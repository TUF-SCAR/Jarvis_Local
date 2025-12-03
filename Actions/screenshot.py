import re
from pathlib import Path


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def next_screenshot_path(base_dir: str | Path, ext: str = ".png") -> Path:
    base = Path(base_dir)
    _ensure_dir(base)
    pat = re.compile(
        rf"^screenshot\s+(\d+)\.{re.escape(ext.lstrip('.'))}$", re.IGNORECASE)

    max_n = 0
    for p in base.iterdir():
        if not p.is_file():
            continue
        m = pat.match(p.name)
        if not m:
            continue
        try:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
        except ValueError:
            pass

    n = max_n + 1
    while True:
        cand = base / f"screenshot {n}{ext}"
        if not cand.exists():
            return cand
        n += 1
