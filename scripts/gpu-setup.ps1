# Optional helper to wire CUDA 12.x + cuDNN 9 on PATH (and optionally copy cuDNN DLLs into CUDA bin)
# Run via gpu-setup.cmd or directly in an Admin PowerShell

$ErrorActionPreference = "Stop"

function Ensure-Admin {
  $cur = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not $cur.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must be run as Administrator."
  }
}
Ensure-Admin

function Add-PathFront([string]$p) {
  if (-not (Test-Path $p)) { return }
  $cur = [Environment]::GetEnvironmentVariable("Path","Machine")
  if ($null -eq $cur) { $cur = "" }
  if ($cur -notlike "*$p*") {
    [Environment]::SetEnvironmentVariable("Path", "$p;$cur", "Machine")
    Write-Host "Added to system PATH: $p"
  } else {
    Write-Host "Already on PATH: $p"
  }
}

Write-Host ""
Write-Host "=== Jarvis GPU Setup (CUDA 12.x + cuDNN 9) ==="
Write-Host ""

# Detect CUDA 12.x bin
$cudaBase = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
$cudaBin  = $null
if (Test-Path $cudaBase) {
  $cands = Get-ChildItem $cudaBase -Directory | Where-Object { $_.Name -like 'v12.*' } | Sort-Object Name -Descending
  foreach ($d in $cands) {
    $b = Join-Path $d.FullName "bin"
    if (Test-Path (Join-Path $b "cublas64_12.dll")) { $cudaBin = $b; break }
  }
}
if (-not $cudaBin) {
  Write-Warning "CUDA 12.x not found. Install CUDA 12.4 first."
  exit 1
}
Write-Host "CUDA bin: $cudaBin"

# Detect cuDNN 9 (CUDA-12 build)
$cudnnBase = "C:\Program Files\NVIDIA\CUDNN"
$cudnnBin  = $null
if (Test-Path $cudnnBase) {
  $bins = Get-ChildItem $cudnnBase -Directory -Recurse -ErrorAction SilentlyContinue | Where-Object {
    $_.FullName -match '\\bin\\12\.' -and (Get-ChildItem $_.FullName -Filter 'cudnn*_9.dll' -ErrorAction SilentlyContinue)
  } | Sort-Object FullName -Descending
  if ($bins) { $cudnnBin = $bins[0].FullName }
}
if ($cudnnBin) {
  Write-Host "cuDNN bin: $cudnnBin"
} else {
  Write-Warning "cuDNN 9 (CUDA-12 build) not found under $cudnnBase. You can still add CUDA bin; copy cuDNN later."
}

# Option A: add both to PATH
Add-PathFront $cudaBin
if ($cudnnBin) { Add-PathFront $cudnnBin }

# Option B: (optional) copy cuDNN DLLs into CUDA bin
if ($cudnnBin) {
  try {
    Copy-Item (Join-Path $cudnnBin "cudnn*_9.dll") -Destination $cudaBin -Force
    Write-Host "Copied cuDNN DLLs into: $cudaBin"
  } catch {
    Write-Warning "Copy failed (need Admin?). PATH entries alone are fine."
  }
}

Write-Host ""
Write-Host "Done. Open a NEW terminal and verify:"
Write-Host "  where cublas64_12.dll"
Write-Host "  where cudnn_ops64_9.dll"
Write-Host ""
Write-Host "GPU test:"
Write-Host "  python -c ""from faster_whisper import WhisperModel; WhisperModel('tiny', device='cuda', compute_type='float16'); print('CUDA OK')"""
