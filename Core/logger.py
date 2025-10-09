import os
from datetime import datetime, timedelta

LOG_DIR = r"D:\Jarvis\Logs"
LOG_FILE = os.path.join(LOG_DIR, "jarvis_log.txt")
LOG_RETENTION_DAYS = 7

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)


def _parse_line_timestamp(line: str):
    """
    Lines look like:
    [YYYY-MM-DD HH:MM:SS] ACTION: ...
    Returns datetime or None if unparsable.
    """
    try:
        if not line.startswith("["):
            return None
        end = line.find("]")
        if end == -1:
            return None
        ts_str = line[1:end].strip()
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def prune_old_logs(retention_days: int = LOG_RETENTION_DAYS):
    """Remove log lines older than retention_days from the single log file."""
    try:
        if not os.path.exists(LOG_FILE):
            return

        cutoff = datetime.now() - timedelta(days=retention_days)
        kept_lines = []

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                ts = _parse_line_timestamp(line)
                # Keep if no timestamp (to be safe) or timestamp is recent
                if ts is None or ts >= cutoff:
                    kept_lines.append(line)

        # Only rewrite if something changed
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(kept_lines)

    except Exception:
        # Never crash Jarvis because of logging cleanup
        pass


def log_action(action: str, result: str = "SUCCESS", message: str = ""):
    """Logs a Jarvis action with timestamp and result."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] ACTION: {action} → {result}"
    if message:
        log_entry += f" ({message})"

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write(log_entry + "\n")
    except Exception:
        # As a last resort, try to create dir again and retry once
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as file:
                file.write(log_entry + "\n")
        except Exception:
            # Swallow to avoid crashing caller
            pass

    # Lightweight heuristic: if file grew big, prune (keeps cost low)
    try:
        if os.path.getsize(LOG_FILE) > 1_000_000:  # ~1MB
            prune_old_logs()
    except Exception:
        pass
