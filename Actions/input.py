import pyautogui


def type_text(text: str, interval: float = 0.1):
    pyautogui.typewrite(text, interval=interval)
