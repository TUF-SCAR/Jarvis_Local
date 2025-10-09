import pyautogui
import time

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


def type_text(text: str = "Jarvis Local test successful.", delay: float = 0.05):
    """
    Simple typing function — works as before.
    """
    if not text:
        return "No text"

    pyautogui.typewrite(text, interval=delay)
    return f"Typed {len(text)} chars"
