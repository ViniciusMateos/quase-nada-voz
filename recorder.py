import io
import wave

import numpy as np
import sounddevice as sd

from logger import log

SAMPLE_RATE = 16000
SILENCE_PEAK_THRESHOLD = 200


def resolve_device_index(device_name):
    """Acha o indice de um dispositivo de entrada pelo nome salvo.
    Retorna None (= dispositivo padrao do sistema) se vazio ou nao achar."""
    if not device_name:
        return None
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0 and dev.get("name") == device_name:
            return idx
    return None


def list_input_devices():
    """Lista (nome, index) dos dispositivos de entrada disponiveis."""
    return [
        (dev["name"], idx)
        for idx, dev in enumerate(sd.query_devices())
        if dev.get("max_input_channels", 0) > 0
    ]


class Recorder:
    """Captura audio do microfone. Enquanto `recording` estiver ligado,
    acumula frames e atualiza `level` (0..1) a cada bloco, pra quem
    quiser desenhar um waveform/vu-meter em tempo real."""

    def __init__(self, on_level=None, device_name=None):
        self.recording = False
        self.level = 0.0
        self._frames = []
        self._on_level = on_level
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=resolve_device_index(device_name),
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if not self.recording:
            return
        self._frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        self.level = min(1.0, rms / 4000.0)
        if self._on_level:
            self._on_level(self.level)

    def start(self):
        self._frames = []
        self.level = 0.0
        self.recording = True

    def stop(self):
        """Para de gravar e retorna os bytes de um WAV mono 16khz/16bit,
        ou None se nao capturou nada."""
        self.recording = False
        self.level = 0.0
        if not self._frames:
            log("Nenhum audio capturado")
            return None

        audio_data = np.concatenate(self._frames, axis=0)
        self._frames = []

        peak = int(np.abs(audio_data).max()) if audio_data.size else 0
        log(f"Audio: {len(audio_data) / SAMPLE_RATE:.1f}s, pico {peak}")
        if peak < SILENCE_PEAK_THRESHOLD:
            log("Microfone praticamente mudo - checar dispositivo padrao do Windows")

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        return wav_io.getvalue()

    def open_stream(self):
        self._stream.start()

    def close_stream(self):
        self._stream.stop()
