import win32com.client


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def speak(text, rate=0, volume=100):
    if text is None:
        text = " "
    text = str(text)
    rate = _clamp(int(rate), -10, 10)
    volume = _clamp(int(volume), 0, 100)
    v = win32com.client.Dispatch("SAPI.SpVoice")
    v.Rate = rate
    v.Volume = volume
    v.Speak(text)
