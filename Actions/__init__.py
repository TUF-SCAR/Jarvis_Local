from .desktop import open_vscode, open_youtube, take_screenshot
from .input import type_text as typing_test  # keep the name used in your flow

ACTIONS = {
    "open_vscode": open_vscode,
    "open_youtube": open_youtube,
    "typing_test": typing_test,
    "take_screenshot": take_screenshot,
}
