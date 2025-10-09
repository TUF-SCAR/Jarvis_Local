# jarvis_main.py
# Jarvis Local — clean UX, robust command parsing, free-form typing, and intents on/off.
# Screenshots go to ./Screenshots with incremental names: "screenshot 1.png", "screenshot 2.png", ...
#
# Highlights:
# - Say: open app <label> / open site <label> / open <anything>
# - Say: type <text>  (exactly types that text; no Enter)
# - "intents" command understands: intent / intents / intense / show intents / list intents
# - Aliases + fuzzy matching for many popular apps/sites
# - Apps/sites can be enabled/disabled in Config/intents.json (old string format still works)
# - Help & banners consistently say: Say 'stop' to exit.

import os
import time
import json
import re
import glob
from time import perf_counter
from pathlib import Path

from Core.tts import say
from Actions import ACTIONS
from Core.logger import log_action, prune_old_logs
from Core.config import cfg_get

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------
# CUDA/cuDNN PATH bootstrap (Windows) — helps GPU users without touching system PATH
# ---------------------------------------------------------------------


def _bootstrap_cuda_path():
    if os.name != "nt":
        return
    added = []
    cuda_base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if Path(cuda_base).exists():
        for vdir in sorted(Path(cuda_base).glob("v12.*"), reverse=True):
            bin_dir = vdir / "bin"
            if (bin_dir / "cublas64_12.dll").exists():
                if str(bin_dir) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = str(
                        bin_dir) + os.pathsep + os.environ.get("PATH", "")
                    added.append(str(bin_dir))
                break
    cudnn_bins = []
    for p in glob.glob(r"C:\Program Files\NVIDIA\CUDNN\*\bin\12.*"):
        bp = Path(p)
        if bp.exists() and list(bp.glob("cudnn*_9.dll")):
            cudnn_bins.append(bp)
    if cudnn_bins:
        cudnn_bin = sorted(cudnn_bins, reverse=True)[0]
        if str(cudnn_bin) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(cudnn_bin) + \
                os.pathsep + os.environ.get("PATH", "")
            added.append(str(cudnn_bin))
    if added:
        print("[CUDA bootstrap] Added to PATH:")
        for a in added:
            print(f"  + {a}")
    else:
        print("[CUDA bootstrap] Using CPU or PATH already OK.")


_bootstrap_cuda_path()

# ---------------------------------------------------------------------
# Optional voice backend
# ---------------------------------------------------------------------
VoiceCommandListener = None
try:
    from Core.voice_whisper import VoiceCommandListener
except Exception:
    VoiceCommandListener = None

# ---------------------------------------------------------------------
# Whitelist (create friendly default)
# ---------------------------------------------------------------------


def load_whitelist(path: str | Path = ROOT / "whitelist.txt") -> set[str]:
    path = Path(path)
    if not path.exists():
        path.write_text(
            "open_vscode\n"
            "open_youtube\n"
            "typing_test\n"
            "take_screenshot\n"
            "say\n"
            "type_text\n",
            encoding="utf-8"
        )
    cmds: set[str] = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            cmds.add(ln)
    return cmds

# ---------------------------------------------------------------------
# Intents loader (supports two formats)
#   v1: "apps": { "vs code": "C:/Path/Code.exe", ... }
#   v2: "apps": { "vs code": {"path":"...","enabled":true,"aliases":["vsc","code"]}, ... }
# Same for "sites" (use key "url" instead of "path" if you prefer).
# ---------------------------------------------------------------------


def _normalize_entry(label: str, v, is_site: bool):
    """
    Returns {target:str, enabled:bool, aliases:list[str]}
    """
    if isinstance(v, str):
        return {
            "target": v,
            "enabled": True,
            "aliases": []
        }
    if isinstance(v, dict):
        target = v.get("url") if is_site else v.get("path")
        if not target:
            target = v.get("target", "")
        enabled = bool(v.get("enabled", True))
        aliases = [a.strip().lower()
                   for a in v.get("aliases", []) if isinstance(a, str)]
        return {"target": target or "", "enabled": enabled, "aliases": aliases}
    return {"target": "", "enabled": False, "aliases": []}


def load_intents(path: str | Path) -> dict:
    try:
        p = Path(path)
        if not p.exists():
            return {"apps": {}, "sites": {}}
        data = json.loads(p.read_text(encoding="utf-8"))
        apps_raw = data.get("apps") or {}
        sites_raw = data.get("sites") or {}

        apps: dict[str, dict] = {}
        sites: dict[str, dict] = {}
        for k, v in apps_raw.items():
            apps[k.strip().lower()] = _normalize_entry(k, v, is_site=False)
        for k, v in sites_raw.items():
            sites[k.strip().lower()] = _normalize_entry(k, v, is_site=True)

        return {"apps": apps, "sites": sites}
    except Exception as e:
        log_action("Load Intents", "ERROR", str(e))
        return {"apps": {}, "sites": {}}

# ---------------------------------------------------------------------
# Local fallback typing (injects into ACTIONS as 'type_text' if missing)
# ---------------------------------------------------------------------


def _inject_type_text_action():
    if "type_text" in ACTIONS:
        return

    def _type_text_impl(text: str):
        try:
            import pyautogui
        except Exception as e:
            raise RuntimeError(
                "Typing requires 'pyautogui'. Install: pip install pyautogui") from e
        pyautogui.typewrite(text, interval=0.02)

    ACTIONS["type_text"] = _type_text_impl


_inject_type_text_action()

# ---------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------


def step(announce: str, action=None, *args, **kwargs):
    start = perf_counter()
    try:
        say(announce)
        if action:
            result = action(*args, **kwargs)
            log_action(announce, "SUCCESS", f"{perf_counter() - start:.2f}s")
            return result
        log_action(announce, "SUCCESS", f"{perf_counter() - start:.2f}s")
    except Exception as e:
        log_action(announce, "ERROR", f"{perf_counter() - start:.2f}s | {e}")
        say(f"Error: {announce}. Check console for details.")
        raise


def safe_step(action_name: str | None, announce: str, *args, **kwargs):
    whitelist = load_whitelist()
    if action_name and action_name not in whitelist:
        msg = f"Blocked. '{action_name}' is not in whitelist."
        say(msg)
        log_action(announce, "BLOCKED", msg)
        return None
    func = ACTIONS.get(action_name) if action_name else None
    return step(announce, func, *args, **kwargs)


def retry_step(action_name: str, announce: str, retries: int = 1, wait_s: float = 1.0, *args, **kwargs):
    try:
        return safe_step(action_name, announce, *args, **kwargs)
    except Exception:
        if retries <= 0:
            raise
        time.sleep(wait_s)
        return retry_step(action_name, f"{announce} (retry)", retries=retries - 1, wait_s=wait_s, *args, **kwargs)


# ---------------------------------------------------------------------
# Normalization — robust mishear fixes (commands included)
# ---------------------------------------------------------------------
COMMON_NORMALIZE = {
    # command words
    r"\bintense\b": "intents",
    r"\bintent\b": "intents",
    r"\bintents?\b": "intents",
    r"\bshow intents?\b": "intents",
    r"\blist intents?\b": "intents",
    r"\bhelps?\b": "help",
    r"\bhalp\b": "help",
    r"\bstop now\b": "stop",
    r"\bquit now\b": "stop",

    # open mishears
    r"\bhop(?:e|ing)\b": "open",
    r"\bhope (?:and|n)\b": "open",

    # youtube variants
    r"\byou dude\b": "youtube",
    r"\byou doob\b": "youtube",
    r"\bu ?tube\b": "youtube",
    r"\byou tube\b": "youtube",
    r"\byou two\b": "youtube",
    r"\byou to\b": "youtube",
    r"\byou\-?tube\b": "youtube",
    r"\byoutub?e?\b": "youtube",

    # vs code variants
    r"\bvia scored\b": "visual studio code",
    r"\bv ?as scored\b": "visual studio code",
    r"\bwe scored\b": "visual studio code",
    r"\bvs good\b": "visual studio code",
    r"\bvs gold\b": "visual studio code",
    r"\bvs code\b": "visual studio code",
    r"\bv ?s ?code\b": "visual studio code",
    r"\bvsc\b": "visual studio code",
    r"\bcode editor\b": "visual studio code",

    # typing variants
    r"\btyping best\b": "typing test",
    r"\btype in test\b": "typing test",
    r"\btype test\b": "typing test",
    r"\btight\b": "type",
    r"\btype in\b": "type ",
}

# Popular aliases — extendable; user intents can add their own aliases too.
ALIASES_SITE = {
    "youtube": ["youtube", "yt", "you tube", "u tube", "you dude", "you doob", "you two", "you to"],
    "google": ["google", "search", "chrome search"],
    "gmail": ["gmail", "g mail"],
    "drive": ["google drive", "drive"],
    "docs": ["google docs", "docs"],
    "sheets": ["google sheets", "sheets"],
    "slides": ["google slides", "slides"],
    "gpt": ["chat gpt", "chatgpt", "openai chat", "g p t"],
    "github": ["git hub", "github"],
    "reddit": ["reddit"],
    "twitter": ["twitter", "x"],
    "instagram": ["instagram", "insta"],
    "facebook": ["facebook", "fb"],
    "whatsapp web": ["whatsapp web", "whatsapp"],
    "spotify web": ["spotify web", "spotify site"],
    "netflix": ["netflix"],
    "prime video": ["amazon prime", "prime video"],
    "steam store": ["steam store", "steam site"]
}
ALIASES_APP = {
    "vs code": ["visual studio code", "v s code", "vs code", "code editor", "code", "vsc"],
    "chrome": ["chrome", "google chrome", "the browser", "browser"],
    "edge": ["microsoft edge", "edge"],
    "notepad": ["notepad", "note pad"],
    "obs": ["obs", "o b s", "obs studio"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "telegram": ["telegram", "tg"],
    "steam": ["steam"],
    "epic games": ["epic", "epic games"],
    "whatsapp": ["whatsapp", "whats app"],
    "notion": ["notion"],
    "figma": ["figma"],
    "photoshop": ["photoshop", "adobe photoshop"],
    "premiere": ["premiere", "adobe premiere", "premiere pro"],
    "after effects": ["after effects", "adobe after effects"],
    "word": ["word", "microsoft word"],
    "excel": ["excel", "microsoft excel"],
    "powerpoint": ["powerpoint", "microsoft powerpoint"]
}


def apply_common_normalize(text: str) -> str:
    s = text
    for pattern, repl in COMMON_NORMALIZE.items():
        s = re.sub(pattern, repl, s)
    return s


def normalize_transcript(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(jarvis|hey jarvis|hey|ok|okay)\s+", "", s)
    s = re.sub(
        r"\b(please|kindly|could you|can you|will you|would you)\b", "", s).strip()
    s = apply_common_normalize(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def make_alias_index(aliases: dict) -> dict:
    idx = {}
    for label, variants in aliases.items():
        for v in variants:
            idx[v.strip().lower()] = label
    return idx


def _charbigram_similarity(a: str, b: str) -> float:
    a2 = set(zip(a, a[1:])) if len(a) > 1 else set()
    b2 = set(zip(b, b[1:])) if len(b) > 1 else set()
    if not a2 and not b2:
        return 1.0 if a == b else 0.0
    inter = len(a2 & b2)
    union = len(a2 | b2) or 1
    return inter / union


def _resolve_from_entries(spoken: str, entries: dict, extra_aliases_index: dict) -> str | None:
    """entries: {label: {target,enabled,aliases}}"""
    s = spoken.lower().strip()

    # Custom aliases from intents.json (only for enabled entries)
    custom_alias_index = {}
    for lab, meta in entries.items():
        if not meta.get("enabled", True):
            continue
        for a in meta.get("aliases", []) or []:
            custom_alias_index[a] = lab

    # 1) direct match on custom aliases
    if s in custom_alias_index:
        return custom_alias_index[s]

    # 2) direct match on built-in aliases
    if s in extra_aliases_index:
        return extra_aliases_index[s]

    # 3) direct label if enabled
    if s in entries and entries[s].get("enabled", True):
        return s

    # 4) fuzzy over all aliases (custom+built-in)
    all_alias_keys = list(custom_alias_index.keys()) + \
        list(extra_aliases_index.keys())
    best, best_score = None, 0.0
    for key in all_alias_keys:
        sc = _charbigram_similarity(s, key)
        if sc > best_score:
            best, best_score = key, sc
    if best and best_score >= 0.76:
        return (custom_alias_index.get(best) or extra_aliases_index.get(best))

    # 5) fuzzy over labels (only enabled)
    labels = [lab for lab, meta in entries.items() if meta.get("enabled", True)]
    best, best_score = None, 0.0
    for lab in labels:
        sc = _charbigram_similarity(s, lab)
        if sc > best_score:
            best, best_score = lab, sc
    if best and best_score >= 0.72:
        return best

    # 6) partial contains (substring) as a last resort
    for lab in labels:
        if s in lab or lab in s:
            return lab

    return None


ALIASES_SITE_INDEX = make_alias_index(ALIASES_SITE)
ALIASES_APP_INDEX = make_alias_index(ALIASES_APP)

# ---------------------------------------------------------------------
# Screenshot naming helpers (incremental files in a folder)
# ---------------------------------------------------------------------


def get_screenshots_dir() -> Path:
    # Use cwd so screenshots follow where you run Jarvis from; configurable via settings.
    base = Path(os.getcwd())
    folder_name = str(
        cfg_get("screenshots_dir", "Screenshots")) or "Screenshots"
    target = base / folder_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def next_screenshot_path(ext: str = ".png") -> Path:
    """
    Returns the next available path like:
      ./Screenshots/screenshot 1.png
      ./Screenshots/screenshot 2.png
      ...
    Robust scan (case-insensitive), and double-check for collisions.
    """
    dir_ = get_screenshots_dir()
    # Build a tolerant regex that ignores case and only matches "screenshot <num>.<ext>"
    ext_clean = re.escape(ext.lstrip("."))
    pattern = re.compile(
        rf"^screenshot\s+(\d+)\.{ext_clean}$", flags=re.IGNORECASE)

    max_n = 0
    for entry in dir_.iterdir():
        if not entry.is_file():
            continue
        m = pattern.match(entry.name)
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                pass

    n = max_n + 1
    # In case of any race/odd files, keep incrementing until a free name is found.
    while True:
        candidate = dir_ / f"screenshot {n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


# ---------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------
HELP_TEXT = (
    "Commands:\n"
    "  open app <label>       -> open an app from Config/intents.json\n"
    "  open site <label>      -> open a site from Config/intents.json\n"
    "  open <anything>        -> resolves to site first, then app (aliases + fuzzy)\n"
    "  type <text>            -> type the exact text in the active window\n"
    "  screenshot             -> save a screenshot to ./Screenshots (auto-numbered)\n"
    "  say <message>          -> speak a message with TTS\n"
    "  intents                -> list available labels (enabled/disabled)\n"
    "  help                   -> show this help\n"
    "  stop                   -> exit\n"
)

# ---------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------


def parse_command(cmd: str, screenshot_name: str, intents: dict):
    s = cmd.strip()

    # meta
    if re.fullmatch(r"(help|\?)", s, flags=re.IGNORECASE):
        return ("__internal_help__", None, None)
    if re.fullmatch(r"(stop|exit|quit)", s, flags=re.IGNORECASE):
        return ("__internal_exit__", None, None)
    if re.fullmatch(r"(intents?|intense|show intents?|list intents?)", s, flags=re.IGNORECASE):
        return ("__internal_intents__", None, None)

    # quick demos (still supported)
    if s.lower() == "open vscode":
        return ("open_vscode", "Opening Visual Studio Code.", [])
    if s.lower() == "open youtube":
        return ("open_youtube", "Opening YouTube in the default browser.", [])

    # screenshot (now auto path)
    if s.lower() == "screenshot":
        return ("__take_screenshot_auto__", "Taking a screenshot.", None)

    # say <message>
    m = re.match(r"^\s*say\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        return ("__internal_say__", m.group(1).strip(), None)

    # type <text>
    m = re.match(r"^\s*type\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        return ("__type_text__", m.group(1).strip(), None)

    # open app <label>
    m = re.match(r"^\s*open\s+app\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        label = _resolve_from_entries(
            label_spoken, intents.get("apps", {}), ALIASES_APP_INDEX)
        return ("__open_app__", (label or label_spoken), None)

    # open site <label>
    m = re.match(r"^\s*open\s+site\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        label = _resolve_from_entries(
            label_spoken, intents.get("sites", {}), ALIASES_SITE_INDEX)
        return ("__open_site__", (label or label_spoken), None)

    # open <anything>
    m = re.match(r"^\s*open\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        site_label = _resolve_from_entries(
            label_spoken, intents.get("sites", {}), ALIASES_SITE_INDEX)
        if site_label:
            return ("__open_site__", site_label, None)
        app_label = _resolve_from_entries(
            label_spoken, intents.get("apps", {}), ALIASES_APP_INDEX)
        if app_label:
            return ("__open_app__", app_label, None)
        return ("__internal_unknown__", label_spoken, None)

    return ("__internal_unknown__", None, None)

# ---------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------


def run_cli(screenshot_name: str, defaults: dict, intents: dict):
    say("Command mode. Type 'help' for commands. Type 'stop' to exit.")
    print("\n--- Jarvis Local • Command Mode ---")
    print("Type 'help' for commands. Type 'stop' to exit.\n")
    while True:
        try:
            raw = input("jarvis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not raw:
            continue
        if not handle_command(raw, screenshot_name, defaults, intents):
            break


def run_voice(screenshot_name: str, defaults: dict, intents: dict, voice_cfg: dict):
    if VoiceCommandListener is None:
        say("Voice modules not available. Switching to command mode.")
        run_cli(screenshot_name, defaults, intents)
        return

    wc_kwargs = dict(
        model_path=str(voice_cfg.get("whisper_model_path", "") or ""),
        sample_rate=int(voice_cfg.get("sample_rate", 16000)),
        silence_seconds=float(voice_cfg.get("silence_seconds", 0.6)),
        phrase_timeout=float(voice_cfg.get("phrase_timeout", 3.0)),
        input_device=voice_cfg.get("input_device", None),
        whisper_model_name=str(voice_cfg.get("whisper_model", "small")),
        compute_type=str(voice_cfg.get("compute_type", "auto")),
        device=str(voice_cfg.get("device", "auto")),
        frame_ms=int(voice_cfg.get("frame_ms", 20)),
        energy_threshold_db=float(voice_cfg.get("energy_threshold_db", -45.0)),
        min_phrase_ms=int(voice_cfg.get("min_phrase_ms", 280)),
        debug_audio=bool(voice_cfg.get("debug_audio", True)),
        show_devices=bool(voice_cfg.get("show_devices", True)),
        warmup_seconds=float(voice_cfg.get("warmup_seconds", 1.0)),
        cpu_threads=int(voice_cfg.get("cpu_threads", 4)),
        num_workers=int(voice_cfg.get("num_workers", 1)),
    )

    listener = VoiceCommandListener(**wc_kwargs)

    say("Voice mode. Say a command. Say 'stop' to exit.")
    print("\n--- Jarvis Local • Voice Mode ---")
    print("Say a command, e.g.:")
    print("  open app vs code   |  open site youtube  |  type hello world")
    print("  screenshot         |  say hello          |  intents  |  help")
    print("Say 'stop' to exit.\n")

    for result in listener.listen_forever():
        if not result or not result.text:
            continue
        raw = result.text
        text = normalize_transcript(raw)
        if not text:
            continue
        print(f"🎤 You said: {text}")
        if text in ("stop", "exit", "quit"):
            say("Goodbye.")
            break
        if not handle_command(text, screenshot_name, defaults, intents):
            break

# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------


def _open_target(label: str, target: str):
    try:
        os.startfile(target)
        log_action("Open Target", "SUCCESS", f"{label} -> {target}")
        return True
    except Exception as e:
        log_action("Open Target", "ERROR", f"{label} | {e}")
        raise


def handle_command(raw: str, screenshot_name: str, defaults: dict, intents: dict) -> bool:
    action, announce, args = parse_command(raw, screenshot_name, intents)

    if action == "__internal_help__":
        print(HELP_TEXT)
        return True

    if action == "__internal_exit__":
        return False

    if action == "__internal_intents__":
        def _fmt(group: dict):
            lines = []
            for lab in sorted(group.keys()):
                meta = group[lab]
                mark = "ON " if meta.get("enabled", True) else "OFF"
                lines.append(f"  - {lab} [{mark}] -> {meta.get('target', '')}")
            return "\n".join(lines) or "  (none)"
        print("\nApps:\n" + _fmt(intents.get("apps", {})))
        print("\nSites:\n" + _fmt(intents.get("sites", {})) + "\n")
        return True

    if action == "__internal_say__":
        msg = (announce or "").strip()
        if msg:
            step(msg, None)
        return True

    if action == "__type_text__":
        text = (announce or "").strip()
        if not text:
            say("Nothing to type.")
            return True
        safe_step("type_text", f"Typing: {text}", text)
        return True

    if action == "__take_screenshot_auto__":
        # Compute next unique path in Screenshots folder
        path = next_screenshot_path(ext=".png")
        safe_step("take_screenshot", "Taking a screenshot.", str(path))
        say(f"Screenshot saved as {path.name}.")
        log_action("Screenshot", "SUCCESS", path.name)
        return True

    if action == "__internal_unknown__":
        spoken = (announce or "").strip().lower()
        if spoken:
            site_label = _resolve_from_entries(
                spoken, intents.get("sites", {}), ALIASES_SITE_INDEX)
            if site_label:
                meta = intents["sites"][site_label]
                if not meta.get("enabled", True):
                    say(f"'{site_label}' is disabled in intents.")
                    return True
                say(f"Opening {site_label}.")
                _open_target(site_label, meta["target"])
                return True
            app_label = _resolve_from_entries(
                spoken, intents.get("apps", {}), ALIASES_APP_INDEX)
            if app_label:
                meta = intents["apps"][app_label]
                if not meta.get("enabled", True):
                    say(f"'{app_label}' is disabled in intents.")
                    return True
                say(f"Opening {app_label}.")
                _open_target(app_label, meta["target"])
                return True
        say("Sorry, I didn't catch that. Say 'help' for commands.")
        print("Unknown command. Say 'help' for the list.")
        return True

    # Built-ins
    if action == "open_vscode":
        safe_step("open_vscode", "Opening Visual Studio Code.")
        time.sleep(defaults["delay_vscode"])
        return True

    if action == "open_youtube":
        safe_step("open_youtube", "Opening YouTube in the default browser.")
        time.sleep(defaults["delay_youtube"])
        return True

    if action == "typing_test":
        retry_step(
            "typing_test", "Typing a test sentence in the active window.", retries=1, wait_s=1.0)
        time.sleep(defaults["delay_typing"])
        return True

    if action == "take_screenshot":
        # Fallback path (should rarely be used now)
        path = args[0] if args else str(next_screenshot_path(ext=".png"))
        safe_step("take_screenshot", "Taking a screenshot.", path)
        say(f"Screenshot saved as {os.path.basename(path)}.")
        log_action("Screenshot", "SUCCESS", os.path.basename(path))
        return True

    if action == "__open_app__":
        label = (announce or "").strip().lower()
        meta = intents.get("apps", {}).get(label)
        if not meta:
            say(f"No app intent found for '{label}'.")
            log_action("Open App", "MISSING", label)
            return True
        if not meta.get("enabled", True):
            say(f"'{label}' is disabled in intents.")
            return True
        say(f"Opening {label}.")
        _open_target(label, meta["target"])
        return True

    if action == "__open_site__":
        label = (announce or "").strip().lower()
        meta = intents.get("sites", {}).get(label)
        if not meta:
            say(f"No site intent found for '{label}'.")
            log_action("Open Site", "MISSING", label)
            return True
        if not meta.get("enabled", True):
            say(f"'{label}' is disabled in intents.")
            return True
        say(f"Opening {label}.")
        _open_target(label, meta["target"])
        return True

    say("That action is not available.")
    return True

# ---------------------------------------------------------------------
# System test (your timings preserved; now uses auto screenshot path)
# ---------------------------------------------------------------------


def run_system_test(defaults: dict):
    safe_step(None, "Starting system test for Jarvis Local.")
    log_action("System Test", "STARTED")

    safe_step("open_vscode", "Opening Visual Studio Code.")
    time.sleep(defaults["delay_vscode"])

    safe_step("open_youtube", "Opening YouTube in the default browser.")
    time.sleep(defaults["delay_youtube"])

    retry_step("typing_test", "Typing a test sentence in the active window.",
               retries=1, wait_s=1.0)
    time.sleep(defaults["delay_typing"])

    shot_path = next_screenshot_path(ext=".png")
    safe_step("take_screenshot", "Taking a screenshot.", str(shot_path))
    say(f"Screenshot saved as {shot_path.name}.")
    log_action("Screenshot", "SUCCESS", shot_path.name)

    safe_step(None, "All tests completed successfully.")
    log_action("System Test", "COMPLETED", "All steps executed successfully.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__ == "__main__":
    try:
        delay_vscode = float(cfg_get("delays.after_vscode", 1.5))
        delay_youtube = float(cfg_get("delays.after_youtube", 2.5))
        delay_typing = float(cfg_get("delays.after_typing", 0.8))
        # Keep 'screenshot_name' in config for backwards-compat, but it's no longer used for naming.
        screenshot_name = str(
            cfg_get("screenshot_name", "jarvis_screenshot.png"))

        mode = str(cfg_get("mode", "voice")).lower()
        intents_path = cfg_get("intents_file", str(
            ROOT / "Config" / "intents.json"))
        intents = load_intents(intents_path)

        voice_cfg = {
            "whisper_model": str(cfg_get("voice.whisper_model", "small")),
            "whisper_model_path": str(cfg_get("voice.whisper_model_path", "")),
            "compute_type": str(cfg_get("voice.compute_type", "auto")),
            "device": str(cfg_get("voice.device", "auto")),
            "sample_rate": int(cfg_get("voice.sample_rate", 16000)),
            "silence_seconds": float(cfg_get("voice.silence_seconds", 0.6)),
            "phrase_timeout": float(cfg_get("voice.phrase_timeout", 3.0)),
            "frame_ms": int(cfg_get("voice.frame_ms", 20)),
            "energy_threshold_db": float(cfg_get("voice.energy_threshold_db", -45.0)),
            "min_phrase_ms": int(cfg_get("voice.min_phrase_ms", 280)),
            "input_device": cfg_get("voice.input_device", None),
            "debug_audio": bool(cfg_get("voice.debug_audio", True)),
            "show_devices": bool(cfg_get("voice.show_devices", True)),
            "warmup_seconds": float(cfg_get("voice.warmup_seconds", 1.0)),
            "cpu_threads": int(cfg_get("voice.cpu_threads", 4)),
            "num_workers": int(cfg_get("voice.num_workers", 1)),
        }

        defaults = {
            "delay_vscode": delay_vscode,
            "delay_youtube": delay_youtube,
            "delay_typing": delay_typing,
            # legacy (not used for naming anymore)
            "screenshot_name": screenshot_name,
        }

        prune_old_logs()

        if mode == "voice":
            log_action("Voice Mode", "STARTED")
            run_voice(screenshot_name, defaults, intents, voice_cfg)
            log_action("Voice Mode", "COMPLETED")
        elif mode == "interactive":
            log_action("Command Mode", "STARTED")
            run_cli(screenshot_name, defaults, intents)
            log_action("Command Mode", "COMPLETED")
        else:
            run_system_test(defaults)

        prune_old_logs()
        print(f"\n✅ Done. (Mode: {mode})")

    except Exception as e:
        log_action("Fatal", "FAILED", str(e))
        say("A fatal error occurred. Please check the logs.")
