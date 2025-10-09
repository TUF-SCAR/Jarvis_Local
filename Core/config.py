import json
from pathlib import Path

CFG_PATH = Path(__file__).resolve().parents[1] / "Config" / "settings.json"
_cached = None


def _load():
    global _cached
    if _cached is not None:
        return _cached
    try:
        if CFG_PATH.exists():
            _cached = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        else:
            _cached = {}
    except Exception:
        _cached = {}
    return _cached


def cfg_get(path: str, default=None):
    data = _load()
    cur = data
    try:
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur
    except Exception:
        return default
