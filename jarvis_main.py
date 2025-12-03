import os
import re
import json
import time
from pathlib import Path

from Core.tts import speak
from Core.logger import log_line
from Actions.registry import dispatch
from Actions.security import load_whitelist
from Actions.screenshot import next_screenshot_path

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "Config" / "settings.json"
INTENTS_PATH = ROOT / "Config" / "intents.json"
WHITELIST_PATH = ROOT / "whitelist.txt"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


DEFAULTS = {
    "voice_rate": 0,
    "voice_volume": 100,
    "announce_only_filename": True,
    "screenshot_dir": str(ROOT),
    "screenshot_name": "jarvis_screenshot.png",
    "screenshots_dir": str(ROOT / "Screenshots"),
    "delays": {"after_vscode": 1.5, "after_youtube": 2.5, "after_typing": 0.8},
    "log_path": str(ROOT / "logs" / "jarvis_log.txt")
}


def load_settings() -> dict:
    s = DEFAULTS.copy()
    data = _read_json(SETTINGS_PATH)
    for k, v in data.items():
        if k == "delays" and isinstance(v, dict):
            d = s["delays"].copy()
            d.update(v)
            s["delays"] = d
        else:
            s[k] = v
    return s


def load_intents() -> dict:
    data = _read_json(INTENTS_PATH)
    if "apps" not in data:
        data["apps"] = {}
    if "sites" not in data:
        data["sites"] = {}
    return data


HELP = (
    "\nCommands:\n"
    "  open app <label>       | open site <label> | open <anything>\n"
    "  type <text>            | screenshot        | screenshot name <file.png>\n"
    "  help                   | stop\n"
)


def parse_command(text: str, intents: dict):
    s = text.strip()
    if re.fullmatch(r"(help|\?)", s, re.I):
        return ("__help__", {})
    if re.fullmatch(r"(stop|exit|quit)", s, re.I):
        return ("__exit__", {})

    m = re.match(r"^\s*open\s+app\s+(.+)$", s, re.I)
    if m:
        return ("open_app", {"app": m.group(1).strip()})

    m = re.match(r"^\s*open\s+site\s+(.+)$", s, re.I)
    if m:
        return ("open_site", {"site": m.group(1).strip()})

    m = re.match(r"^\s*open\s+(.+)$", s, re.I)
    if m:
        spoken = m.group(1).strip().lower()
        if spoken in intents.get("sites", {}):
            return ("open_site", {"site": spoken})
        if spoken in intents.get("apps", {}):
            return ("open_app", {"app": spoken})
        return ("__unknown__", {"raw": spoken})

    m = re.match(r"^\s*type\s+(.+)$", s, re.I)
    if m:
        return ("type_text", {"text": s[m.start(1):]})

    if s.lower() == "screenshot":
        return ("__screenshot_auto__", {})
    m = re.match(r"^\s*screenshot\s+name\s+(.+)$", s, re.I)
    if m:
        return ("screenshot", {"name": m.group(1).strip()})

    return ("__unknown__", {"raw": s})


def main():
    settings = load_settings()
    intents = load_intents()
    whitelist = load_whitelist(str(WHITELIST_PATH))

    speak("Jarvis Local ready.",
          settings["voice_rate"], settings["voice_volume"])
    print(HELP)

    while True:
        try:
            raw = input("jarvis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not raw:
            continue

        action, args = parse_command(raw, intents)

        if action == "__help__":
            print(HELP)
            continue
        if action == "__exit__":
            speak("Stopping Jarvis Local.",
                  settings["voice_rate"], settings["voice_volume"])
            break
        if action == "__screenshot_auto__":
            shots_dir = settings.get("screenshots_dir", "./Screenshots")
            p = next_screenshot_path(shots_dir, ".png")
            tmp_settings = dict(settings)
            tmp_settings["screenshot_dir"] = str(p.parent)
            dispatch("screenshot", {"name": p.name},
                     tmp_settings, whitelist, intents)
            log_line(settings["log_path"], "SCREENSHOT", p.name, "OK")
            continue

        if action == "__unknown__":
            speak("I did not understand.",
                  settings["voice_rate"], settings["voice_volume"])
            continue

        result = dispatch(action, args, settings, whitelist, intents)
        status = "OK" if result.get("ok") else "FAIL"
        log_line(settings["log_path"], action.upper(), str(args), status)


if __name__ == "__main__":
    main()
