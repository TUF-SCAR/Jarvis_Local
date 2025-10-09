# Global installer (Admin). Installs Python deps globally and lays down config templates.
# Double-click via install.cmd

$ErrorActionPreference = "Stop"

function Ensure-Admin {
  $cur = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not $cur.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Elevating to Administrator..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo "powershell"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $psi.Verb = "runas"
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    exit
  }
}
Ensure-Admin

function Get-PyCmd {
  try { & py -V | Out-Null; return "py" } catch {}
  try { & python -V | Out-Null; return "python" } catch {}
  throw "Python was not found on PATH. Install Python 3 and re-run."
}

Write-Host ""
Write-Host "=== Jarvis Local - Global Installer ==="
Write-Host ""

# Repo root is parent of the scripts folder
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $repoRoot)) { throw "Repo root not found. ($repoRoot)" }

# 1) Ensure Python (try winget if totally missing)
$pyLauncherOk = $false
try { & py -V | Out-Null; $pyLauncherOk = $true } catch {}
if (-not $pyLauncherOk) {
  $pythonOk = $false
  try { & python -V | Out-Null; $pythonOk = $true } catch {}
  if (-not $pythonOk) {
    Write-Host "Python not found. Attempting to install Python 3 via winget..."
    try {
      winget install -e --id Python.Python.3 -h
    } catch {
      throw "Python not found and winget install failed. Please install Python 3 manually and re-run."
    }
  }
}

$py = Get-PyCmd
Write-Host "Using Python via: $py"

# 2) Upgrade pip + install packages globally
Write-Host ""
Write-Host "Installing/upgrading global Python packages..."
& $py -m pip install --upgrade pip

$req = Join-Path $repoRoot "requirements.txt"
if (Test-Path $req) {
  & $py -m pip install -r $req
} else {
  # Fallback inline list if requirements.txt missing
  & $py -m pip install `
    faster-whisper==1.2.0 `
    sounddevice==0.5.2 `
    "av>=11" `
    "numpy>=1.26" `
    "coloredlogs>=15.0.1" `
    "typing_extensions>=4.7"
}

# 3) Create config files if missing
$configDir = Join-Path $repoRoot "Config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$settingsDefault = Join-Path $configDir "settings.default.json"
$settingsUser    = Join-Path $configDir "settings.json"
$intentsSample   = Join-Path $configDir "intents.sample.json"
$intentsUser     = Join-Path $configDir "intents.json"

if (-not (Test-Path $settingsDefault)) {
@'
{
  "delays": {
    "after_vscode": 1.5,
    "after_youtube": 2.5,
    "after_typing": 0.8
  },
  "screenshot_name": "jarvis_screenshot.png",
  "mode": "voice",
  "intents_file": "Config/intents.json",
  "routine_file": null,
  "voice": {
    "backend": "whisper",
    "whisper_model": "small",
    "whisper_model_path": "",
    "device": "cpu",
    "compute_type": "auto",
    "sample_rate": 16000,
    "silence_seconds": 0.6,
    "phrase_timeout": 3.0,
    "frame_ms": 20,
    "energy_threshold_db": -45.0,
    "min_phrase_ms": 280,
    "cpu_threads": 4,
    "num_workers": 1,
    "input_device": null,
    "show_devices": true,
    "debug_audio": true,
    "warmup_seconds": 1.0
  }
}
'@ | Set-Content -Encoding UTF8 $settingsDefault
  Write-Host "Wrote Config/settings.default.json"
}

if (-not (Test-Path $settingsUser)) {
  Copy-Item $settingsDefault $settingsUser
  Write-Host "Created Config/settings.json (edit voice.device: cpu or gpu)"
} else {
  Write-Host "Config/settings.json already exists - keeping it."
}

if (-not (Test-Path $intentsSample)) {
@'
{
  "apps": {
    "vs code": "C:/Users/yourname/AppData/Local/Programs/Microsoft VS Code/Code.exe",
    "notepad": "C:/Windows/system32/notepad.exe",
    "chrome": "C:/Program Files/Google/Chrome/Application/chrome.exe"
  },
  "sites": {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gpt": "https://chat.openai.com"
  }
}
'@ | Set-Content -Encoding UTF8 $intentsSample
  Write-Host "Wrote Config/intents.sample.json"
}

if (-not (Test-Path $intentsUser)) {
  Copy-Item $intentsSample $intentsUser
  Write-Host "Created Config/intents.json (edit labels/paths/urls)"
} else {
  Write-Host "Config/intents.json already exists - keeping it."
}

Write-Host ""
Write-Host "Install complete."
Write-Host "Next: edit Config/settings.json and set voice.device to cpu or gpu."
Write-Host "To run: double-click run.cmd (or: $py jarvis_main.py)"
