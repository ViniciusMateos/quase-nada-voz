import io
import threading
import wave

import numpy as np
import sounddevice as sd

import paths
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


def _close_quietly(stream):
    try:
        stream.stop()
        stream.close()
    except Exception:
        pass


class Recorder:
    """Captura audio do microfone. Enquanto `recording` estiver ligado,
    acumula frames e chama `on_bands` a cada bloco com os niveis (0..1)
    de N_BANDS faixas de frequencia, pra desenhar um equalizador ao vivo
    (mostra so o nivel atual, sem historico/scroll).

    Abre um stream NOVO a cada gravacao e fecha no fim. Antes o stream
    ficava aberto direto desde que o app subia -- depois de dias rodando
    (suspensao do USB do headset, queda do acesso remoto) ele continuava
    entregando audio com nivel plausivel, mas corrompido: a API recebia
    fala e devolvia vazio ou lixo. Abrir custa ~80ms, menos do que alguem
    leva pra comecar a falar depois de apertar a tecla -- e de brinde o
    microfone fica livre enquanto nao esta gravando."""

    def __init__(self, on_bands=None, device_name=None):
        self.recording = False
        self._frames = []
        self._on_bands = on_bands
        self._device_name = device_name
        self._stream = None
        # cada gravacao ganha um numero; stream/callback de uma gravacao
        # que ja acabou (toque rapido, stream antigo ainda fechando) se
        # reconhece como velho e nao mistura audio na gravacao atual.
        self._session = 0
        self._lock = threading.Lock()
        self._driver_warnings = set()

    def _make_callback(self, session):
        def callback(indata, frames, time_info, status):
            if status:
                self._driver_warnings.add(str(status).strip())
            if not self.recording or session != self._session:
                return
            self._frames.append(indata.copy())
            if self._on_bands:
                self._on_bands(_compute_bands(indata))
        return callback

    def start(self):
        """Nao bloqueia: e chamado de dentro do hook de teclado global, e
        o Windows remove o hook em silencio se ele demorar pra responder.
        Abrir o microfone (que pode levar bem mais que 80ms se o USB
        estiver acordando) acontece numa thread separada."""
        with self._lock:
            self._session += 1
            session = self._session
            self._frames = []
            self._driver_warnings = set()
            self.recording = True
        threading.Thread(target=self._open, args=(session,), daemon=True).start()

    def _open(self, session):
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                device=resolve_device_index(self._device_name),
                callback=self._make_callback(session),
            )
            stream.start()
        except Exception as e:
            log(f"Falha ao abrir o microfone: {e}")
            return
        with self._lock:
            if session == self._session and self.recording:
                self._stream = stream
                return
        # a gravacao ja acabou enquanto o microfone abria
        _close_quietly(stream)

    def stop(self):
        """Para de gravar e retorna os bytes de um WAV mono 16khz/16bit,
        ou None se nao capturou nada."""
        with self._lock:
            self.recording = False
            self._session += 1
            stream, self._stream = self._stream, None
            frames, self._frames = self._frames, []
            warnings = self._driver_warnings
        if stream is not None:
            # fechar espera o driver -- fora do hook de teclado tambem
            threading.Thread(target=_close_quietly, args=(stream,), daemon=True).start()
        if warnings:
            log(f"Avisos do driver de audio durante a gravacao: {', '.join(sorted(warnings))}")

        if not frames:
            log("Nenhum audio capturado")
            return None

        audio_data = np.concatenate(frames, axis=0)

        peak = int(np.abs(audio_data).max()) if audio_data.size else 0
        rms = int(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))) if audio_data.size else 0
        log(f"Audio: {len(audio_data) / SAMPLE_RATE:.1f}s, pico {peak}, rms {rms}")
        if peak < SILENCE_PEAK_THRESHOLD:
            log("Microfone praticamente mudo - checar dispositivo padrao do Windows")

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        data = wav_io.getvalue()

        if paths.IS_DEV:
            # so no Dev: guarda a ultima gravacao pra dar pra ouvir/analisar
            # quando a transcricao vier vazia (sobrescreve sempre)
            try:
                (paths.DATA_DIR / "ultima_gravacao.wav").write_bytes(data)
            except OSError:
                pass
        return data

    def open_stream(self):
        # o stream agora abre sob demanda em start() -- mantido so pra
        # nao quebrar quem chama
        pass

    def close_stream(self):
        with self._lock:
            self.recording = False
            self._session += 1
            stream, self._stream = self._stream, None
        if stream is not None:
            _close_quietly(stream)
