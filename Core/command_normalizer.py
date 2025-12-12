import re

FILLER_PHRASES = [
    "please",
    "kindly",
    "could you",
    "can you",
    "will you",
    "would you"
]

WAKE_PHRASES = [
    "jarvis",
    "hey jarvis",
    "ok jarvis",
    "okay jarvis"
]

COMMAND_SYNONYMS = {
    "help":    ["help", "?", "halp"],
    "intents": ["intents", "intent", "intense", "show intents", "list intents"],
    "stop":    ["stop", "exit", "quit", "stop now"]
}


def normalize_text(raw):
    """Lowercase, remove wake words + filler phrases, collapse spaces."""
    if raw is None:
        return ""
    s = str(raw).lower().strip()
    if not s:
        return ""

    for ww in WAKE_PHRASES:
        ww_l = ww.lower()
        if s.startswith(ww_l + " "):
            s = s[len(ww_l):].lstrip()
            break

    for fp in FILLER_PHRASES:
        fp_l = fp.lower()
        s = s.replace(" " + fp_l + " ", " ")

    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_command_word(text):
    """
    For full-line commands like 'help', 'intense', 'stop now'.
    Returns the canonical word if it matches a synonym, otherwise returns text.
    """
    t = (text or "").lower().strip()
    for canonical, variants in COMMAND_SYNONYMS.items():
        if t in variants:
            return canonical
    return t


def _extract_intent_meta(group):
    """
    group: intents["apps"] or intents["sites"]

    Supports:
      "label": "target"
      "label": {"target": "...", "aliases": [...], "enabled": true/false}

    Returns:
      labels: set of canonical labels
      target_map: label -> target
      alias_index: alias -> label
    """
    labels = set()
    target_map = {}
    alias_index = {}

    if not isinstance(group, dict):
        return labels, target_map, alias_index

    for label, val in group.items():
        label_norm = str(label).strip().lower()
        labels.add(label_norm)

        if isinstance(val, str):
            target_map[label_norm] = val
            continue

        if isinstance(val, dict):
            target = val.get("target") or val.get("path") or val.get("url")
            if target:
                target_map[label_norm] = target
            for al in val.get("aliases", []) or []:
                alias_index[str(al).strip().lower()] = label_norm

    return labels, target_map, alias_index


def _char_bigram_similarity(a, b):
    """Simple character bigram Jaccard similarity."""
    a = (a or "").lower()
    b = (b or "").lower()
    if not a and not b:
        return 1.0
    if a == b:
        return 1.0

    a_bi = {a[i:i+2] for i in range(len(a) - 1)} if len(a) > 1 else {a}
    b_bi = {b[i:i+2] for i in range(len(b) - 1)} if len(b) > 1 else {b}

    if not a_bi or not b_bi:
        return 0.0

    inter = len(a_bi & b_bi)
    uni = len(a_bi | b_bi)
    if uni == 0:
        return 0.0
    return inter / uni


def resolve_label(spoken, group):
    """
    spoken: what user said ("vs good", "you tube", "gothub")
    group: intents["apps"] or intents["sites"]

    Returns:
      canonical label string, or None if no good match.
    """
    if not spoken:
        return None
    s = str(spoken).strip().lower()

    labels, target_map, alias_index = _extract_intent_meta(group)

    if not labels and not alias_index:
        return None

    if s in alias_index:
        return alias_index[s]

    if s in labels:
        return s

    best_label = None
    best_score = 0.0
    for alias, lab in alias_index.items():
        sc = _char_bigram_similarity(s, alias)
        if sc > best_score:
            best_label, best_score = lab, sc
    if best_label is not None and best_score >= 0.75:
        return best_label

    best_label = None
    best_score = 0.0
    for lab in labels:
        sc = _char_bigram_similarity(s, lab)
        if sc > best_score:
            best_label, best_score = lab, sc
    if best_label is not None and best_score >= 0.7:
        return best_label

    for lab in labels:
        if s in lab or lab in s:
            return lab

    return None
