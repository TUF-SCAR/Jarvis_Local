import os
import webbrowser
import pyautogui


def open_app(path_or_name: str):
    os.startfile(path_or_name)


def open_site(url: str):
    webbrowser.open(url)


def take_screenshot(save_dir: str, filename: str) -> str:
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, filename)
    pyautogui.screenshot(out_path)
    return out_path
