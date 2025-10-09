import os
import webbrowser
from datetime import datetime
from pathlib import Path
import pyautogui  # used for screenshot only

# --- Direct open VS Code (no CMD, no subprocess) ---


def open_vscode():
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     r"Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]

    for exe in candidates:
        if exe and os.path.exists(exe):
            os.startfile(exe)  # direct open, no console
            return "VS Code launched"

    # fallback: try CLI if nothing else found
    os.startfile("code")

# --- Direct open YouTube ---


def open_youtube():
    webbrowser.open("https://www.youtube.com")
    return "YouTube opened"

# --- Screenshot using PyAutoGUI ---


def take_screenshot(filename=None):
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"jarvis_screenshot_{ts}.png"
    path = Path.cwd() / filename
    pyautogui.screenshot(str(path))
    return filename
