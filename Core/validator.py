import json
from pathlib import Path
import time
from .tts import speak

ROOT = Path(__file__).resolve().parents[1]   # -> D:\Jarvis
CONFIG = ROOT / "config" / "settings.json"


def _load_settings():
    if CONFIG.exists():
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    # fallback defaults
    return {
        "safe_mode": True,
        "log_file": "logs/jarvis_log.txt",
        "whitelist_file": "whitelist.txt"
    }


def _ensure_parents(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def load_whitelist():
    settings = _load_settings()
    wl_path = ROOT / settings.get("whitelist_file", "whitelist.txt")
    if not wl_path.exists():
        # create a minimal whitelist if missing
        wl_path.write_text("say\n", encoding="utf-8")
        speak("Whitelist file missing. I created a new one with 'say' only.")
    commands = set()
    for line in wl_path.read_text(encoding="utf-8").splitlines():
        cmd = line.strip()
        if cmd and not cmd.startswith("#"):
            commands.add(cmd)
    return commands


def _log(line: str):
    settings = _load_settings()
    log_path = ROOT / settings.get("log_file", "logs/jarvis_log.txt")
    _ensure_parents(log_path)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {line}\n")


def validate_plan(plan: dict) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    settings = _load_settings()
    whitelist = load_whitelist()

    action = (plan or {}).get("action")
    if not action:
        return False, "No action in plan."

    if settings.get("safe_mode", True) and action not in whitelist:
        return False, f"Action '{action}' is not in whitelist."

    return True, "OK"


def execute_plan(plan: dict, actions: dict):
    """Validate → run mapped function → log + voice feedback."""
    ok, reason = validate_plan(plan)
    action = (plan or {}).get("action", "UNKNOWN")
    args = (plan or {}).get("args", {})

    if not ok:
        speak(f"Blocked: {reason}")
        _log(f"BLOCK {action} {args} :: {reason}")
        return

    func = actions.get(action)
    if not func:
        msg = f"Action '{action}' is allowed but not implemented."
        speak(msg)
        _log(f"MISS {action} {args} :: not implemented")
        return

    _log(f"RUN  {action} {args}")
    try:
        result = func(**args)
        _log(f"DONE {action} :: {result!r}")
    except TypeError as e:
        speak("Argument mismatch for this action.")
        _log(f"ERR  {action} {args} :: {e}")
    except Exception as e:
        speak("There was an error while executing the action.")
        _log(f"ERR  {action} {args} :: {e}")
