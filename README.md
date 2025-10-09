````markdown
<h1 align="center">🧠 Jarvis-Local</h1>

<p align="center">
⚡ <b>Your privacy-first offline PC assistant — built to obey, not to spy.</b><br>
<i>Voice-controlled desktop automations powered entirely by local Python modules.</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" />
  <img src="https://img.shields.io/badge/Status-MVP%20Working-brightgreen" />
  <img src="https://img.shields.io/badge/Privacy-100%25%20Offline-black" />
</p>

---

## ✨ What It Does (MVP)

- 🎙️ Speaks actions with **Windows SAPI (win32com)** — _synchronous voice, no pyttsx3, no beeps_
- 🪟 Automates your desktop: **open apps**, **open websites**, **type text**, **take screenshots**
- ✅ **Whitelist guard** (`whitelist.txt`) so only approved apps/sites can be executed
- 🧱 **No CMD popups** — uses `os.startfile()` directly
- 🗃️ **Logger (WIP)** → `Logs/jarvis_log.txt` records actions & outcomes
- 🔌 Clean, extendable structure (add new actions in minutes)

---

## 🗂️ Project Structure

```bash
D:\Jarvis
│  jarvis_main.py
│  whitelist.txt
│
├─ Actions
│   ├─ __init__.py
│   ├─ desktop.py        # open apps/sites/files
│   └─ input.py          # typing & automation
│
├─ Core
│   └─ tts.py            # Windows SAPI voice engine (win32com)
│
├─ Config
│   └─ settings.json     # optional settings (e.g., voice rate, screenshot name)
│
└─ Logs
    └─ jarvis_log.txt    # (WIP) persistent logger
```
````

---

## 🧭 System Test Flow (what you’ll see & what happens)

```text
"Starting system test for Jarvis Local."
"Opening Visual Studio Code."                    → opens VS Code
"Opening YouTube in the default browser."        → opens YouTube
"Typing a test sentence in the active window."   → types into focused window
"Taking a screenshot."                           → saves jarvis_screenshot.png
"Screenshot saved as jarvis_screenshot.png."
"All tests completed successfully."
```

> 💡 Tip: For typing to work, **click the input box** of the active window once (Jarvis types wherever your OS text caret is).

---

## ⚙️ Prerequisites

- **Windows 10/11**

- **Python 3.10+** installed **globally** (no venv needed, by design)

- **Packages (install globally):**

  ```powershell
  pip install pywin32 pyautogui
  ```

  > `time` and `os` are built-in; no install required.

- **Permissions:** Run your terminal as **Administrator** if any permission prompts block automation.

---

## 🚀 Quick Start (Copy–Paste)

```powershell
# 1) Clone
git clone https://github.com/TUF-SCAR/Jarvis_Local.git
cd Jarvis_Local

# 2) Install required packages (global)
pip install pywin32 pyautogui

# 3) (Optional) Create Config/settings.json
#    Only if you want to override defaults (see sample below)

# 4) Add your allowed apps/sites in whitelist.txt (sample below)

# 5) Run
python jarvis_main.py
```

---

## ✅ Whitelist Setup

`D:\Jarvis\whitelist.txt`
Put **one entry per line**. Supports **apps**, **folders/files**, and **domains**.

**Examples**

```
# Apps (full paths or common names your code maps to)
C:\Users\YourName\AppData\Local\Programs\Microsoft VS Code\Code.exe
chrome.exe
notepad.exe

# Websites (only these will open)
https://www.youtube.com
https://github.com

# Files/folders you explicitly allow
D:\Jarvis\Screenshots
D:\Docs\Notes.txt
```

> 🔒 Jarvis will **only** execute items that pass `safe_step()` checks against this whitelist.

---

## 🛠️ settings.json (optional)

Create `D:\Jarvis\Config\settings.json` to override defaults:

```json
{
  "voice_rate": 0, // -10 (slow) to +10 (fast); 0 is default
  "voice_volume": 100, // 0-100
  "screenshot_name": "jarvis_screenshot.png",
  "screenshot_dir": "D:\\Jarvis", // where screenshots save
  "announce_only_filename": true, // speak only the filename, not full path
  "open_method": "os.startfile", // keep as is (no subprocess)
  "test_phrase": "Typing test from Jarvis Local."
}
```

---

## 🧩 Core Concepts (How It Works)

### 1) Voice (Windows SAPI)

```python
# Core/tts.py (concept)
import win32com.client

def speak(text, rate=0, volume=100):
    v = win32com.client.Dispatch("SAPI.SpVoice")
    v.Rate = rate
    v.Volume = volume
    v.Speak(text)
```

### 2) Open Apps & Sites (no CMD popups)

```python
# Actions/desktop.py (concept)
import os
import webbrowser

def open_app(path_or_name):
    # after whitelist validation
    os.startfile(path_or_name)

def open_website(url):
    # after whitelist validation
    webbrowser.open(url)
```

### 3) Typing (active window)

```python
# Actions/input.py (concept)
import pyautogui

def type_text(text):
    pyautogui.typewrite(text, interval=0.02)  # click the input box first!
```

### 4) Screenshot

```python
# Actions/desktop.py (concept)
import pyautogui, os

def take_screenshot(save_dir, filename):
    path = os.path.join(save_dir, filename)
    pyautogui.screenshot(path)
    return path
```

### 5) Logger (WIP)

```python
# Logs/jarvis_log.txt (example line format)
# [2025-10-09 17:42:01] OK  | OPEN_APP     | "Code.exe"
# [2025-10-09 17:42:03] OK  | OPEN_SITE    | "https://youtube.com"
# [2025-10-09 17:42:05] OK  | TYPE_TEXT    | "Typing test from Jarvis Local."
# [2025-10-09 17:42:08] OK  | SCREENSHOT   | "D:\Jarvis\jarvis_screenshot.png"
```

---

## 🧪 Run the Built-In System Test

```powershell
python jarvis_main.py --test
```

What it should do (in order):

1. Speak: **“Starting system test for Jarvis Local.”**
2. Open **VS Code**
3. Open **YouTube** in your default browser
4. Type the configured **test phrase** in the active window
5. Take a screenshot → **`jarvis_screenshot.png`**
6. Speak only the **filename** (not the full path)
7. Speak: **“All tests completed successfully.”**

---

## 🧱 Add Your Own Actions (Extending Jarvis)

1. Create a new file in `Actions/`, e.g. `media.py`
2. Add functions (make them small & single-purpose)
3. Import and wire them in `jarvis_main.py`
4. Add whitelist entries if needed

**Example:**

```python
# Actions/media.py
import pyautogui

def volume_up(steps=2):
    for _ in range(steps):
        pyautogui.press('volumeup')
```

---

## 🛟 Troubleshooting

- **“It says it typed, but nothing typed.”**
  Click into the target input box so the OS caret is visible, then run again.

- **Voice sounds too slow/fast.**
  Tune `voice_rate` in `Config/settings.json` (from -10 to +10).

- **CMD window appears.**
  Ensure app launching uses **`os.startfile()`** (not `subprocess`).

- **Screenshot path spoken fully.**
  Set `"announce_only_filename": true` in `settings.json`.

- **Not opening an app/site.**
  Confirm it exists in **`whitelist.txt`** (full path or whitelisted domain).

- **Permission errors.**
  Try a terminal with **Run as Administrator**.

---

## 🔒 Philosophy

> “A personal assistant should serve you — not send your data away.”

Jarvis-Local is built for **speed, privacy, and local control**, making it the perfect base for an **offline AI desktop companion**.

---

## 🙌 Credits

Built with love in India 🇮🇳 by **[TUF_SCAR](https://github.com/TUF-SCAR)**

---

```

```
