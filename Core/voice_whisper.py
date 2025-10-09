# Core/voice_whisper.py
# Offline voice listener using faster-whisper + sounddevice.
# - Single-switch device: "gpu"/"cpu"/"auto" + compute_type="auto"
# - Auto compute on GPU: try float16 -> int8_float16 -> float32
# - CPU compute: int8
# - Simple energy VAD, mic picker, warmup meter

import queue
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except Exception as e:
    raise RuntimeError(
        "sounddevice import failed. Run: pip install sounddevice") from e

try:
    from faster_whisper import WhisperModel
except Exception as e:
    raise RuntimeError(
        "faster-whisper import failed. Run: pip install faster-whisper") from e


@dataclass
class ASRResult:
    text: str


def _rms(frame_i16: np.ndarray) -> float:
    if frame_i16.size == 0:
        return 0.0
    f = frame_i16.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(f * f)))


def _pick_input_device(user_choice):
    try:
        devices = sd.query_devices()
    except Exception as e:
        raise RuntimeError(f"Cannot query audio devices: {e}")

    def _print_devices():
        print("\n=== Audio Input Devices ===")
        for idx, d in enumerate(devices):
            if int(d.get("max_input_channels", 0)) > 0:
                print(
                    f"[{idx}] {d.get('name')}  |  in={d.get('max_input_channels')} out={d.get('max_output_channels')}")
        print("===========================\n")

    if user_choice is None:
        try:
            def_in, _ = sd.default.device
        except Exception:
            def_in = None
        if def_in is None or devices[def_in]["max_input_channels"] <= 0:
            _print_devices()
            raise RuntimeError("Default input device has no input channels. "
                               "Set voice.input_device in Config/settings.json to a valid index or name substring.")
        return None  # use default

    if isinstance(user_choice, int):
        if user_choice < 0 or user_choice >= len(devices):
            _print_devices()
            raise RuntimeError(
                f"Input device index {user_choice} out of range.")
        if devices[user_choice]["max_input_channels"] <= 0:
            _print_devices()
            raise RuntimeError(
                f"Device {user_choice} has 0 input channels. Pick another.")
        return user_choice

    if isinstance(user_choice, str):
        needle = user_choice.casefold()
        for idx, d in enumerate(devices):
            name = str(d.get("name", "")).casefold()
            if needle in name and int(d.get("max_input_channels", 0)) > 0:
                print(f"Using input device [{idx}] {d.get('name')}")
                return idx
        _print_devices()
        raise RuntimeError(f"No input device found matching: '{user_choice}'")

    return None


class VoiceCommandListener:
    """
    Phrase listener with energy VAD:
      - Captures mic @ 16k mono int16
      - Segments by silence / timeout
      - Transcribes each phrase with faster-whisper
    """

    def __init__(
        self,
        model_path: str | None = None,
        sample_rate: int = 16000,
        silence_seconds: float = 0.6,
        phrase_timeout: float = 3.0,
        input_device=None,
        whisper_model_name: str = "small",
        compute_type: str = "auto",      # "auto" recommended
        frame_ms: int = 20,
        energy_threshold_db: float = -45.0,
        min_phrase_ms: int = 280,
        device: str = "auto",            # "gpu" | "cpu" | "auto" | "cuda"
        debug_audio: bool = True,
        show_devices: bool = True,
        warmup_seconds: float = 1.0,
        cpu_threads: int = 4,
        num_workers: int = 1,
    ):
        self.sample_rate = int(sample_rate)
        self.frame_ms = int(frame_ms)
        self.frame_samples = int(self.sample_rate * (self.frame_ms / 1000.0))
        self.frame_bytes = self.frame_samples * 2

        self.blocksize = max(self.frame_samples * 4,
                             int(self.sample_rate * 0.08))  # ~80ms
        self.dtype = "int16"
        self.channels = 1

        if show_devices:
            try:
                print("\nAudio device summary (input-capable shown):")
                for idx, d in enumerate(sd.query_devices()):
                    if int(d.get("max_input_channels", 0)) > 0:
                        print(
                            f"  [{idx}] {d.get('name')}  | in={d.get('max_input_channels')} out={d.get('max_output_channels')}")
                print()
            except Exception:
                pass

        self.device = _pick_input_device(input_device)

        self.silence_seconds = float(silence_seconds)
        self.phrase_timeout = float(phrase_timeout)
        self.min_phrase_ms = int(min_phrase_ms)

        self.energy_threshold = 10.0 ** (float(energy_threshold_db) / 20.0)

        self._cpu_threads = int(cpu_threads)
        self._num_workers = int(num_workers)

        # Init Whisper with smart device/compute selection
        self._runtime_device, self._runtime_compute = self._init_model(
            model_path=model_path,
            whisper_model_name=whisper_model_name,
            request_device=str(device).lower(),
            request_compute=str(compute_type).lower(),
        )
        print(
            f"[Whisper] Using device={self._runtime_device}, compute_type={self._runtime_compute}")

        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._stop = False
        self.debug_audio = bool(debug_audio)
        self.warmup_seconds = float(warmup_seconds)

    def _init_model(self, model_path, whisper_model_name, request_device, request_compute):
        """
        Create WhisperModel. Device accepts "gpu"/"cuda"/"cpu"/"auto".
        compute_type "auto" selects best available:
          - GPU: try float16 -> int8_float16 -> float32
          - CPU: int8
        """
        def _make(device, compute):
            kwargs = dict(device=device, compute_type=compute,
                          cpu_threads=self._cpu_threads, num_workers=self._num_workers)
            if model_path:
                p = Path(model_path)
                if not p.exists():
                    raise RuntimeError(f"Whisper model path not found: {p}")
                return WhisperModel(str(p), **kwargs)
            else:
                return WhisperModel(whisper_model_name, **kwargs)

        def _try_gpu_with(compute_list):
            last_err = None
            for comp in compute_list:
                try:
                    m = _make("cuda", comp)
                    self.model = m
                    return "cuda", comp
                except Exception as e:
                    last_err = e
                    print(
                        f"[Whisper] GPU init failed with compute_type='{comp}': {e}")
            raise RuntimeError(last_err or "Unknown GPU init error")

        wants_gpu = request_device in (
            "gpu", "cuda") or request_device == "auto"
        if request_device == "cpu":
            # Force CPU path; ignore requested compute if "auto"
            comp = "int8" if request_compute == "auto" else request_compute
            m = _make("cpu", comp)
            self.model = m
            return "cpu", comp

        # Try GPU first if asked or auto
        if wants_gpu:
            try:
                if request_compute == "auto":
                    # Try best → most compatible
                    return _try_gpu_with(["float16", "int8_float16", "float32"])
                else:
                    # Honor user-specified compute first; on failure, do sensible fallbacks
                    d, c = _try_gpu_with(
                        [request_compute, "int8_float16", "float32"])
                    return d, c
            except Exception as e:
                print(
                    f"[Whisper] CUDA not usable ({e}). Falling back to CPU int8.")
                m = _make("cpu", "int8")
                self.model = m
                return "cpu", "int8"

        # Explicit non-GPU path (if not auto/gpu)
        m = _make("cpu", "int8" if request_compute ==
                  "auto" else request_compute)
        self.model = m
        return "cpu", "int8" if request_compute == "auto" else request_compute

    def _audio_callback(self, indata, frames, time_info, status):
        try:
            self._q.put_nowait(bytes(indata))
        except Exception:
            pass

    def _iter_frames(self, pcm_bytes: bytes):
        n = len(pcm_bytes) // 2
        if n <= 0:
            return
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        for off in range(0, n, self.frame_samples):
            chunk = arr[off: off + self.frame_samples]
            if chunk.size == self.frame_samples:
                yield chunk

    def listen_forever(self):
        stream_kwargs = dict(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            dtype=self.dtype,
            channels=self.channels,
            callback=self._audio_callback,
            device=self.device,
        )

        try:
            with sd.RawInputStream(**stream_kwargs):
                if self.debug_audio and self.warmup_seconds > 0:
                    print(
                        f"[Mic] Warmup {self.warmup_seconds:.1f}s — speak and watch RMS… (threshold ~ {self.energy_threshold:.4f})")
                    t_end = time.time() + self.warmup_seconds
                    last_print = 0.0
                    while time.time() < t_end:
                        try:
                            pcm = self._q.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        level = 0.0
                        for frame in self._iter_frames(pcm):
                            level = max(level, _rms(frame))
                        now = time.time()
                        if now - last_print >= 0.25:
                            bar = "#" * int(min(40, level * 200))
                            print(f"RMS: {level:.4f} {bar}")
                            last_print = now
                    print("[Mic] Warmup done.\n")

                phrase_buf = bytearray()
                last_voiced_ts = time.time()
                phrase_start_ts = None

                while not self._stop:
                    try:
                        pcm = self._q.get(timeout=0.1)
                    except queue.Empty:
                        pcm = None

                    if pcm:
                        for frame in self._iter_frames(pcm):
                            voiced = _rms(frame) >= self.energy_threshold
                            if voiced:
                                phrase_buf.extend(frame.tobytes())
                                last_voiced_ts = time.time()
                                if phrase_start_ts is None:
                                    phrase_start_ts = last_voiced_ts

                    now = time.time()

                    if phrase_buf and (now - last_voiced_ts) >= self.silence_seconds:
                        dur_ms = (len(phrase_buf) / 2) / \
                            self.sample_rate * 1000.0
                        if dur_ms >= self.min_phrase_ms:
                            text = self._transcribe_bytes(bytes(phrase_buf))
                            if text:
                                yield ASRResult(text=text)
                        phrase_buf = bytearray()
                        phrase_start_ts = None
                        continue

                    if phrase_buf and phrase_start_ts and (now - phrase_start_ts) >= self.phrase_timeout:
                        dur_ms = (len(phrase_buf) / 2) / \
                            self.sample_rate * 1000.0
                        if dur_ms >= self.min_phrase_ms:
                            text = self._transcribe_bytes(bytes(phrase_buf))
                            if text:
                                yield ASRResult(text=text)
                        phrase_buf = bytearray()
                        phrase_start_ts = None
        except Exception as e:
            try:
                print("\n[Audio] Available input devices:")
                for idx, d in enumerate(sd.query_devices()):
                    if int(d.get("max_input_channels", 0)) > 0:
                        print(
                            f"  [{idx}] {d.get('name')}  | in={d.get('max_input_channels')} out={d.get('max_output_channels')}")
                print()
            except Exception:
                pass
            raise RuntimeError(
                f"Failed to open microphone stream. {e}\n"
                "Tip: set 'voice.input_device' in Config/settings.json to a valid index or device name substring.\n"
                "Also check Windows microphone privacy settings and default recording device."
            ) from e

    def _transcribe_bytes(self, pcm_bytes: bytes) -> str:
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(
            np.float32) / 32768.0
        segments, _info = self.model.transcribe(
            audio=audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            no_speech_threshold=0.6
        )
        texts = []
        for seg in segments:
            if seg.text:
                texts.append(seg.text.strip())
        return " ".join(texts).strip()

    def stop(self):
        self._stop = True
