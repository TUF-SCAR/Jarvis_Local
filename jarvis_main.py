# jarvis_main.py
import os
import time
import json
import re
import difflib
from time import perf_counter
from pathlib import Path
import glob

from Core.tts import say
from Actions import ACTIONS
from Core.logger import log_action, prune_old_logs
from Core.config import cfg_get

ROOT = Path(__file__).resolve().parent

# ------- CUDA/cuDNN PATH bootstrap (Windows) -------


def _bootstrap_cuda_path():
    if os.name != "nt":
        return
    added = []
    cuda_base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if Path(cuda_base).exists():
        candidates = sorted(Path(cuda_base).glob("v12.*"), reverse=True)
        for vdir in candidates:
            bin_dir = vdir / "bin"
            if (bin_dir / "cublas64_12.dll").exists():
                if str(bin_dir) not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = str(
                        bin_dir) + os.pathsep + os.environ.get("PATH", "")
                    added.append(str(bin_dir))
                break
    cudnn_base = r"C:\Program Files\NVIDIA\CUDNN"
    if Path(cudnn_base).exists():
        cudnn_bins = []
        for p in glob.glob(r"C:\Program Files\NVIDIA\CUDNN\*\bin\12.*"):
            if Path(p).exists() and list(Path(p).glob("cudnn*_9.dll")):
                cudnn_bins.append(Path(p))
        cudnn_bins.sort(reverse=True)
        if cudnn_bins:
            cudnn_bin = cudnn_bins[0]
            if str(cudnn_bin) not in os.environ.get("PATH", ""):
                os.environ["PATH"] = str(cudnn_bin) + \
                    os.pathsep + os.environ.get("PATH", "")
                added.append(str(cudnn_bin))
    if added:
        print("[CUDA bootstrap] Prepending to PATH:")
        for a in added:
            print(f"  + {a}")
    else:
        print("[CUDA bootstrap] No CUDA-12/cuDNN paths added (may already be present).")


_bootstrap_cuda_path()

# ------- Voice backend -------
VoiceCommandListener = None
try:
    from Core.voice_whisper import VoiceCommandListener
except Exception:
    VoiceCommandListener = None

# ------- Whitelist -------


def load_whitelist(path: str | Path = ROOT / "whitelist.txt") -> set[str]:
    path = Path(path)
    if not path.exists():
        path.write_text(
            "open_vscode\nopen_youtube\ntyping_test\ntake_screenshot\nsay\n", encoding="utf-8")
    cmds: set[str] = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            cmds.add(ln)
    return cmds

# ------- Intents -------


def load_intents(path: str | Path) -> dict:
    try:
        p = Path(path)
        if not p.exists():
            return {"apps": {}, "sites": {}}
        data = json.loads(p.read_text(encoding="utf-8"))
        apps = {k.strip().lower(): v for k, v in (
            data.get("apps") or {}).items()}
        sites = {k.strip().lower(): v for k, v in (
            data.get("sites") or {}).items()}
        return {"apps": apps, "sites": sites}
    except Exception as e:
        log_action("Load Intents", "ERROR", str(e))
        return {"apps": {}, "sites": {}}


def safe_open_target(label: str, target: str):
    try:
        os.startfile(target)
        log_action("Open Target", "SUCCESS", f"{label} -> {target}")
        return True
    except Exception as e:
        log_action("Open Target", "ERROR", f"{label} | {e}")
        raise

# ------- Orchestrated step -------


def step(announce: str, action=None, *args, **kwargs):
    start = perf_counter()
    try:
        say(announce)
        if action:
            result = action(*args, **kwargs)
            elapsed = perf_counter() - start
            log_action(announce, "SUCCESS", f"{elapsed:.2f}s")
            return result
        else:
            elapsed = perf_counter() - start
            log_action(announce, "SUCCESS", f"{elapsed:.2f}s")
    except Exception as e:
        elapsed = perf_counter() - start
        log_action(announce, "ERROR", f"{elapsed:.2f}s | {e}")
        say(f"Error during step: {announce}. Check console for details.")
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
        return retry_step(action_name, announce + " (retry)", retries=retries - 1, wait_s=wait_s, *args, **kwargs)


# ------- Normalization / aliases / parser -------
COMMON_NORMALIZE = {
    r"\bhop(?:e|ing)\b": "open",
    r"\bhope and\b": "open",
    r"\bhope n\b": "open",
    r"\byou dude\b": "youtube",
    r"\byou doob\b": "youtube",
    r"\bu ?tube\b": "youtube",
    r"\byou tube\b": "youtube",
    r"\byou two\b": "youtube",
    r"\byou to\b": "youtube",
    r"\byou-tube\b": "youtube",
    r"\byoutub?e?\b": "youtube",
    r"\bvia scored\b": "visual studio code",
    r"\bv ?as scored\b": "visual studio code",
    r"\bwe scored\b": "visual studio code",
    r"\bvs good\b": "visual studio code",
    r"\bvs gold\b": "visual studio code",
    r"\bvs code\b": "visual studio code",
    r"\bv ?s ?code\b": "visual studio code",
    r"\bvsc\b": "visual studio code",
    r"\bcode editor\b": "visual studio code",
    r"\btyping best\b": "typing test",
    r"\btype in test\b": "typing test",
    r"\btype test\b": "typing test",
}
ALIASES_SITE = {
    "youtube": ["youtube", "yt", "you tube", "u tube", "you dude", "you doob", "you two", "you to"],
    "gpt": ["chat gpt", "chatgpt", "g p t", "openai chat"],
    "google": ["google", "chrome search", "browser search"],
    "github": ["git hub", "github"]
}
ALIASES_APP = {
    "vs code": ["visual studio code", "v s code", "vs code", "code editor", "code", "vsc"],
    "chrome": ["chrome", "google chrome", "the browser"],
    "notepad": ["notepad", "note pad"],
    "obs": ["obs", "o b s", "obs studio"],
    "spotify": ["spotify", "music app"]
}


def apply_common_normalize(text: str) -> str:
    s = text
    for pattern, repl in COMMON_NORMALIZE.items():
        # <-- fixed: pass 's' as the input string
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
    index = {}
    for label, variants in aliases.items():
        for v in variants:
            index[v] = label
    return index


ALIASES_SITE_INDEX = make_alias_index(ALIASES_SITE)
ALIASES_APP_INDEX = make_alias_index(ALIASES_APP)


def fuzzy_best_label(spoken: str, labels: list[str], cutoff: float = 0.8) -> str | None:
    best = None
    best_score = 0.0
    for lab in labels:
        score = difflib.SequenceMatcher(None, spoken, lab).ratio()
        if score > best_score:
            best_score = score
            best = lab
    return best if (best is not None and best_score >= cutoff) else None


def resolve_label(spoken: str, label_map: dict, aliases_index: dict) -> str | None:
    s = spoken.lower().strip()
    if s in aliases_index:
        return aliases_index[s]
    if s in label_map:
        return s
    alias_phrases = list(aliases_index.keys())
    match_alias = fuzzy_best_label(s, alias_phrases, cutoff=0.76)
    if match_alias:
        return aliases_index[match_alias]
    match_label = fuzzy_best_label(s, list(label_map.keys()), cutoff=0.72)
    if match_label:
        return match_label
    if s in ("code", "the code", "code app"):
        return "vs code" if "vs code" in label_map else None
    return None


HELP_TEXT = (
    "Commands:\n"
    "  open vscode            -> open Visual Studio Code\n"
    "  open youtube           -> open YouTube in default browser\n"
    "  typing test            -> type the test sentence in the active window\n"
    "  screenshot             -> take a screenshot in current working folder\n"
    "  say <message>          -> TTS speak a message\n"
    "  open app <label>       -> open an app by label from Config/intents.json\n"
    "  open site <label>      -> open a site by label from Config/intents.json\n"
    "  open <anything>        -> tries site first, then app (aliases + fuzzy)\n"
    "  intents                -> list available app/site labels\n"
    "  help                   -> show this help\n"
    "  exit                   -> quit\n"
)


def parse_command(cmd: str, screenshot_name: str, intents: dict):
    s = cmd.strip()
    if s.lower() in ("help", "?"):
        return ("__internal_help__", None, None)
    if s.lower() in ("exit", "quit", "stop"):
        return ("__internal_exit__", None, None)
    if s.lower() == "intents":
        return ("__internal_intents__", None, None)

    if s.lower() == "open vscode":
        return ("open_vscode", "Opening Visual Studio Code.", [])
    if s.lower() == "open youtube":
        return ("open_youtube", "Opening YouTube in the default browser.", [])
    if s.lower() == "typing test":
        return ("typing_test", "Typing a test sentence in the active window.", [])
    if s.lower() == "screenshot":
        path = os.path.join(os.getcwd(), screenshot_name)
        return ("take_screenshot", "Taking a screenshot.", [path])

    m = re.match(r"^\s*say\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        msg = m.group(1).strip()
        return ("__internal_say__", msg, None)

    m = re.match(r"^\s*open\s+app\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        label = resolve_label(label_spoken, intents.get(
            "apps", {}), ALIASES_APP_INDEX)
        return ("__open_app__", (label or label_spoken), None)

    m = re.match(r"^\s*open\s+site\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        label = resolve_label(label_spoken, intents.get(
            "sites", {}), ALIASES_SITE_INDEX)
        return ("__open_site__", (label or label_spoken), None)

    m = re.match(r"^\s*open\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        label_spoken = m.group(1).strip()
        site_label = resolve_label(
            label_spoken, intents.get("sites", {}), ALIASES_SITE_INDEX)
        if site_label:
            return ("__open_site__", site_label, None)
        app_label = resolve_label(
            label_spoken, intents.get("apps", {}), ALIASES_APP_INDEX)
        if app_label:
            return ("__open_app__", app_label, None)
        return ("__internal_unknown__", label_spoken, None)

    return ("__internal_unknown__", None, None)


def run_cli(screenshot_name: str, defaults: dict, intents: dict):
    say("Interactive command mode. Type help to see available commands.")
    print("\n--- Jarvis Local • Command Mode ---")
    print("Type 'help' for commands, 'exit' to quit.\n")
    while True:
        try:
            raw = input("jarvis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not raw:
            continue
        if not handle_command(raw, screenshot_name, defaults, intents):
            break


def run_voice(screenshot_name: str, defaults: dict, intents: dict, voice_cfg: dict):
    if VoiceCommandListener is None:
        say("Voice modules not available. Falling back to command mode.")
        run_cli(screenshot_name, defaults, intents)
        return

    wc_kwargs = dict(
        model_path=str(voice_cfg.get("whisper_model_path", "") or ""),
        sample_rate=int(voice_cfg.get("sample_rate", 16000)),
        silence_seconds=float(voice_cfg.get("silence_seconds", 0.6)),
        phrase_timeout=float(voice_cfg.get("phrase_timeout", 3.0)),
        input_device=voice_cfg.get("input_device", None),
        whisper_model_name=str(voice_cfg.get("whisper_model", "small")),
        compute_type=str(voice_cfg.get("compute_type", "auto")),   # auto
        device=str(voice_cfg.get("device", "auto")
                   ),               # gpu/cpu/auto
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

    say("Voice mode. Say a command. Say stop to exit.")
    print("\n--- Jarvis Local • Voice Mode (Whisper) ---")
    print("Say a command (e.g., 'open youtube', 'open app vs code', 'screenshot', 'say hello').")
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


def handle_command(raw: str, screenshot_name: str, defaults: dict, intents: dict) -> bool:
    action, announce, args = parse_command(raw, screenshot_name, intents)

    if action == "__internal_help__":
        print(HELP_TEXT)
        return True
    if action == "__internal_exit__":
        return False
    if action == "__internal_unknown__":
        spoken = (announce or "").strip().lower()
        if spoken:
            lab = resolve_label(spoken, intents.get(
                "sites", {}), ALIASES_SITE_INDEX)
            if lab and lab in intents["sites"]:
                say(f"Opening {lab}.")
                safe_open_target(lab, intents["sites"][lab])
                return True
            lab = resolve_label(spoken, intents.get(
                "apps", {}), ALIASES_APP_INDEX)
            if lab and lab in intents["apps"]:
                say(f"Opening {lab}.")
                safe_open_target(lab, intents["apps"][lab])
                return True
        say("Sorry, I didn't understand that.")
        print("Unknown command. Say or type 'help' to see the list.")
        return True
    if action == "__internal_say__":
        step(announce, None)
        return True
    if action == "__internal_intents__":
        apps = ", ".join(sorted(intents.get("apps", {}).keys())) or "(none)"
        sites = ", ".join(sorted(intents.get("sites", {}).keys())) or "(none)"
        print(f"\nApps:  {apps}\nSites: {sites}\n")
        return True

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
        safe_step("take_screenshot", "Taking a screenshot.", *(args or []))
        say(f"Screenshot saved as {os.path.basename((args or [''])[0])}.")
        log_action("Screenshot", "SUCCESS",
                   os.path.basename((args or [''])[0]))
        return True

    if action == "__open_app__":
        label = (announce or "").strip().lower()
        target = intents.get("apps", {}).get(label)
        if not target:
            say(f"No app intent found for {label}.")
            log_action("Open App", "MISSING", label)
            return True
        say(f"Opening {label}.")
        safe_open_target(label, target)
        return True

    if action == "__open_site__":
        label = (announce or "").strip().lower()
        target = intents.get("sites", {}).get(label)
        if not target:
            say(f"No site intent found for {label}.")
            log_action("Open Site", "MISSING", label)
            return True
        say(f"Opening {label}.")
        safe_open_target(label, target)
        return True

    say("Action not available.")
    return True


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
    screenshot_path = os.path.join(os.getcwd(), defaults["screenshot_name"])
    safe_step("take_screenshot", "Taking a screenshot.", screenshot_path)
    say(f"Screenshot saved as {defaults['screenshot_name']}.")
    log_action("Screenshot", "SUCCESS", defaults["screenshot_name"])
    safe_step(None, "All tests completed successfully.")
    log_action("System Test", "COMPLETED", "All steps executed successfully.")


if __name__ == "__main__":
    try:
        delay_vscode = float(cfg_get("delays.after_vscode", 1.5))
        delay_youtube = float(cfg_get("delays.after_youtube", 2.5))
        delay_typing = float(cfg_get("delays.after_typing", 0.8))
        screenshot_name = str(
            cfg_get("screenshot_name", "jarvis_screenshot.png"))

        mode = str(cfg_get("mode", "voice")).lower()
        routine_file = cfg_get("routine_file", None)

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
            "screenshot_name": screenshot_name,
        }

        prune_old_logs()

        steps = None
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
