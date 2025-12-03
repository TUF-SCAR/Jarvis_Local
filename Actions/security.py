def load_whitelist(path: str) -> set[str]:
    allowed: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    allowed.add(s.lower())
    except FileNotFoundError:
        pass
    return allowed


def is_allowed_app(target: str, allowed: set[str]) -> bool:
    t = (target or "").lower()
    if t in allowed:
        return True
    for a in allowed:
        if a.endswith(".exe") and t.endswith(a):
            return True
    return False


def is_allowed_site(url: str, allowed: set[str]) -> bool:
    u = (url or "").lower()
    for a in allowed:
        if a.startswith("http") and u.startswith(a):
            return True
    return False
