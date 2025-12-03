import os
import time


def log_line(log_path: str, action: str, detail: str, status: str = "OK"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    folder = os.path.dirname(log_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    line = f'[{ts}] {status:<4}| {action:<12}| "{detail}"\n'
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
