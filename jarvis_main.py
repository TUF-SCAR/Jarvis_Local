import re
import json
from pathlib import Path

from Core.tts import speak
from Core.logger import log_line
from Actions.registry import dispatch
from Actions.security import load_whitelist
from Actions.screenshot import next_screenshot_path
from Core.command_normalizer import normalize_text, normalize_command_word, resolve_label

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "Config" / "settings.json"
INTENTS_PATH = ROOT / "Config" / "intents.json"
WHITELIST_PATH = ROOT / "whitelist.txt"

VoiceCommandListener = None
try:
    from Core.voice_whisper import VoiceCommandListener
except Exception:
    VoiceCommandListener = None


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


DEFAULTS = {
    "mode": "interactive",
    "voice_rate": 0,
    "voice_volume": 100,
    "announce_only_filename": True,
    "screenshot_dir": str(ROOT),
    "screenshot_name": "jarvis_screenshot.png",
    "screenshots_dir": str(ROOT / "Screenshots"),
    "log_path": str(ROOT / "logs" / "jarvis_log.txt"),

    "voice": {
        "whisper_model": "small",
        "whisper_model_path": "",
        "compute_type": "auto",
        "device": "auto",
        "sample_rate": 16000,
        "silence_seconds": 0.6,
        "phrase_timeout": 3.0,
        "frame_ms": 20,
        "energy_threshold_db": -45.0,
        "min_phrase_ms": 280,
        "input_device": None,
        "debug_audio": True,
        "show_devices": True,
        "warmup_seconds": 1.0,
        "cpu_threads": 4,
        "num_workers": 1
    }
}


def load_settings() -> dict:
    s = json.loads(json.dumps(DEFAULTS))
    data = _read_json(SETTINGS_PATH)

    for k, v in data.items():
        if k == "voice" and isinstance(v, dict):
            s["voice"].update(v)
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
    "  intents                | help              | stop\n"
)


def parse_command(text: str, intents: dict):
    s = text.strip()
    lt = s.lower()

    m = re.match(r"^\s*open\s+app\s+(.+)$", s, re.IGNORECASE)
    if m:
        spoken = m.group(1).strip()
        label = resolve_label(spoken, intents.get(
            "apps", {})) or spoken.lower()
        return ("open_app", {"app": label})

    m = re.match(r"^\s*open\s+site\s+(.+)$", s, re.IGNORECASE)
    if m:
        spoken = m.group(1).strip()
        label = resolve_label(spoken, intents.get(
            "sites", {})) or spoken.lower()
        return ("open_site", {"site": label})

    m = re.match(r"^\s*open\s+(.+)$", s, re.IGNORECASE)
    if m:
        spoken = m.group(1).strip()
        site_label = resolve_label(spoken, intents.get("sites", {}))
        if site_label:
            return ("open_site", {"site": site_label})
        app_label = resolve_label(spoken, intents.get("apps", {}))
        if app_label:
            return ("open_app", {"app": app_label})
        return ("__unknown__", {"raw": spoken})

    m = re.match(r"^\s*type\s+(.+)$", s, re.IGNORECASE)
    if m:
        return ("type_text", {"text": s[m.start(1):]})

    if lt == "screenshot":
        return ("__screenshot_auto__", {})

    m = re.match(r"^\s*screenshot\s+name\s+(.+)$", s, re.IGNORECASE)
    if m:
        return ("screenshot", {"name": m.group(1).strip()})

    return ("__unknown__", {"raw": s})


def print_intents(intents: dict):
    apps = intents.get("apps", {})
    sites = intents.get("sites", {})

    print("\nApps:")
    if apps:
        for lab, val in apps.items():
            if isinstance(val, dict):
                target = val.get("target") or val.get("path") or ""
            else:
                target = val
            print(f"  - {lab} -> {target}")
    else:
        print("  (none)")

    print("\nSites:")
    if sites:
        for lab, val in sites.items():
            if isinstance(val, dict):
                target = val.get("target") or val.get("url") or ""
            else:
                target = val
            print(f"  - {lab} -> {target}")
    else:
        print("  (none)")
    print()


def handle_text(raw_text: str, settings: dict, intents: dict, whitelist: set[str]) -> bool:
    """
    Returns False to exit, True to continue.
    """
    rate = settings["voice_rate"]
    vol = settings["voice_volume"]
    log_path = settings["log_path"]

    normalized = normalize_text(raw_text)
    if not normalized:
        return True

    cmd_key = normalize_command_word(normalized)

    if cmd_key == "help":
        print(HELP)
        return True

    if cmd_key == "intents":
        print_intents(intents)
        return True

    if cmd_key == "stop":
        speak("Stopping Jarvis Local.", rate, vol)
        return False

    action, args = parse_command(normalized, intents)

    if action == "__screenshot_auto__":
        shots_dir = settings.get("screenshots_dir", "./Screenshots")
        path = next_screenshot_path(shots_dir, ".png")
        tmp_settings = dict(settings)
        tmp_settings["screenshot_dir"] = str(path.parent)
        dispatch("screenshot", {"name": path.name},
                 tmp_settings, whitelist, intents)
        log_line(log_path, "SCREENSHOT", path.name, "OK")
        return True

    if action == "__unknown__":
        speak("I did not understand.", rate, vol)
        return True

    result = dispatch(action, args, settings, whitelist, intents)
    status = "OK" if result.get("ok") else "FAIL"
    log_line(log_path, action.upper(), str(args), status)
    return True


def run_cli(settings: dict, intents: dict, whitelist: set[str]):
    rate = settings["voice_rate"]
    vol = settings["voice_volume"]
    speak("Command mode. Type help. Type stop to exit.", rate, vol)
    print(HELP)
    while True:
        try:
            raw = input("jarvis> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not handle_text(raw, settings, intents, whitelist):
            break


def run_voice(settings: dict, intents: dict, whitelist: set[str]):
    rate = settings["voice_rate"]
    vol = settings["voice_volume"]

    if VoiceCommandListener is None:
        speak("Voice modules not available. Switching to command mode.", rate, vol)
        run_cli(settings, intents, whitelist)
        return

    vc = settings.get("voice", {}) or {}
    listener = VoiceCommandListener(
        model_path=str(vc.get("whisper_model_path", "") or ""),
        sample_rate=int(vc.get("sample_rate", 16000)),
        silence_seconds=float(vc.get("silence_seconds", 0.6)),
        phrase_timeout=float(vc.get("phrase_timeout", 3.0)),
        input_device=vc.get("input_device", None),
        whisper_model_name=str(vc.get("whisper_model", "small")),
        compute_type=str(vc.get("compute_type", "auto")),
        device=str(vc.get("device", "auto")),
        frame_ms=int(vc.get("frame_ms", 20)),
        energy_threshold_db=float(vc.get("energy_threshold_db", -45.0)),
        min_phrase_ms=int(vc.get("min_phrase_ms", 280)),
        debug_audio=bool(vc.get("debug_audio", True)),
        show_devices=bool(vc.get("show_devices", True)),
        warmup_seconds=float(vc.get("warmup_seconds", 1.0)),
        cpu_threads=int(vc.get("cpu_threads", 4)),
        num_workers=int(vc.get("num_workers", 1)),
    )

    speak("Voice mode. Say a command. Say stop to exit.", rate, vol)
    print("\n--- Jarvis Local • Voice Mode ---")
    print("Say: open yt | open app vscode | type hello | screenshot | intents | help")
    print("Say 'stop' to exit.\n")

    for r in listener.listen_forever():
        if not r or not getattr(r, "text", ""):
            continue
        raw = r.text
        print(f"🎤 Heard: {raw}")
        if not handle_text(raw, settings, intents, whitelist):
            break


def main():
    settings = load_settings()
    intents = load_intents()
    whitelist = load_whitelist(str(WHITELIST_PATH))

    rate = settings["voice_rate"]
    vol = settings["voice_volume"]
    speak("Jarvis Local ready.", rate, vol)

    mode = str(settings.get("mode", "interactive")).lower().strip()
    if mode == "voice":
        run_voice(settings, intents, whitelist)
    else:
        run_cli(settings, intents, whitelist)


if __name__ == "__main__":
    main()
