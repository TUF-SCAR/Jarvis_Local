import pythoncom
import win32com.client

_speaker = None


def _ensure_speaker(rate=1, volume=100):
    global _speaker
    if _speaker is None:
        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        v.Rate = rate        # -10..+10
        v.Volume = volume    # 0..100
        _speaker = v
    return _speaker


def say(text: str):
    if not text:
        return
    sp = _ensure_speaker()
    print(f"[Jarvis]: {text}")
    sp.Speak(text)  # synchronous/blocking
