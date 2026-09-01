import io
import wave

import numpy as np
import sounddevice as sd

from logger import log

SAMPLE_RATE = 16000
SILENCE_PEAK_THRESHOLD = 200

N_BANDS = 5
BAND_MAX_FREQ = 4000  # hz -- cobre a faixa relevante de voz, ignora o resto
BAND_NORMALIZE = 12.0  # divisor empirico pra levar a magnitude da FFT pra 0..1


def _compute_bands(indata):
    """FFT do bloco de audio, dividido em N_BANDS faixas de frequencia
    (graves a agudos) com espacamento log. Retorna niveis 0..1 por faixa,
    pra desenhar um equalizador ao vivo (sem depender de historico)."""
    samples = indata[:, 0].astype(np.float32)
    if samples.size < 8:
        return [0.0] * N_BANDS

    windowed = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), 1 / SAMPLE_RATE)

    max_bin = int(np.searchsorted(freqs, BAND_MAX_FREQ))
    spectrum = spectrum[:max_bin] if max_bin > 1 else spectrum
    if spectrum.size == 0:
        return [0.0] * N_BANDS

    edges = np.unique(np.geomspace(1, spectrum.size, N_BANDS + 1).astype(int))
    bands = []
    for i in range(N_BANDS):
        lo = edges[i] - 1 if i < len(edges) else spectrum.size - 1
        hi = edges[i + 1] if i + 1 < len(edges) else spectrum.size
        chunk = spectrum[max(0, lo):max(hi, lo + 1)]
        magnitude = float(chunk.mean()) if chunk.size else 0.0
        bands.append(min(1.0, magnitude / (BAND_NORMALIZE * len(samples))))
    return bands


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
    """Lista (nome, index) dos dispositivos de entrada disponiveis, um
    por microfone fisico. O PortAudio expõe o mesmo microfone repetido
    uma vez por API de audio (MME, DirectSound, WASAPI, WDM-KS) -- so
    a WASAPI da uma entrada limpa por dispositivo (igual o Windows
    mostra nas configuracoes de som), entao filtra so nela."""
    hostapis = sd.query_hostapis()
    wasapi_idx = next((i for i, api in enumerate(hostapis) if "WASAPI" in api["name"]), None)

    devices = [
        (dev["name"], idx)
        for idx, dev in enumerate(sd.query_devices())
        if dev.get("max_input_channels", 0) > 0
        and (wasapi_idx is None or dev["hostapi"] == wasapi_idx)
    ]
    return devices


class Recorder:
    """Captura audio do microfone. Enquanto `recording` estiver ligado,
    acumula frames e chama `on_bands` a cada bloco com os niveis (0..1)
    de N_BANDS faixas de frequencia, pra desenhar um equalizador ao vivo
    (mostra so o nivel atual, sem historico/scroll)."""

    def __init__(self, on_bands=None, device_name=None):
        self.recording = False
        self._frames = []
        self._on_bands = on_bands
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
        if self._on_bands:
            self._on_bands(_compute_bands(indata))

    def start(self):
        self._frames = []
        self.recording = True

    def stop(self):
        """Para de gravar e retorna os bytes de um WAV mono 16khz/16bit,
        ou None se nao capturou nada."""
        self.recording = False
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
