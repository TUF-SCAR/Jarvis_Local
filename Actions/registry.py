from Core.tts import speak
from Actions.desktop import open_app, open_site, take_screenshot
from Actions.input import type_text
from Actions.security import is_allowed_app, is_allowed_site


def build_registry():
    return {
        "open_app": open_app,
        "open_site": open_site,
        "type_text": type_text,
        "screenshot": take_screenshot,
    }


def dispatch(action: str, args: dict, settings: dict, whitelist: set[str], intents: dict):
    reg = build_registry()

    if action not in reg:
        speak("Unknown action.")
        return {"ok": False, "msg": "unknown_action"}

    if action == "open_app":
        target = args.get("app") or args.get("name")
        if intents and "apps" in intents and target in intents["apps"]:
            meta = intents["apps"][target]
            target = meta["target"] if isinstance(meta, dict) else meta

        if not target:
            speak("No app specified.")
            return {"ok": False, "msg": "no_app"}

        if not is_allowed_app(target, whitelist):
            speak("Blocked. App not in whitelist.")
            return {"ok": False, "msg": "denied"}

        speak(f"Opening {target}.")
        reg[action](target)
        return {"ok": True}

    if action == "open_site":
        url = args.get("url") or args.get("site")
        if intents and "sites" in intents and url in intents["sites"]:
            meta = intents["sites"][url]
            url = meta["target"] if isinstance(meta, dict) else meta

        if not url:
            speak("No site specified.")
            return {"ok": False, "msg": "no_site"}

        if not is_allowed_site(url, whitelist):
            speak("Blocked. Site not in whitelist.")
            return {"ok": False, "msg": "denied"}

        speak("Opening website.")
        reg[action](url)
        return {"ok": True}

    if action == "type_text":
        text = args.get("text", "")
        speak("Typing.")
        reg[action](text, args.get("interval", 0.02))
        return {"ok": True}

    if action == "screenshot":
        save_dir = settings.get("screenshot_dir", ".")
        name = args.get("name") or settings.get(
            "screenshot_name", "jarvis_screenshot.png")
        speak("Taking a screenshot.")
        path = reg[action](save_dir, name)
        if settings.get("announce_only_filename", True):
            from os.path import basename
            speak(f"Screenshot saved as {basename(path)}.")
        else:
            speak(f"Screenshot saved at {path}.")
        return {"ok": True}

    speak("Nothing executed.")
    return {"ok": False, "msg": "no_route"}
