"""Ditados guardados pra transcrever depois.

Sem conta conectada -- ou quando a sessao cai no meio do caminho -- o
audio nao pode simplesmente sumir. A pessoa fala um minuto, manda, e
descobre so ali que precisa entrar na conta: sem isso ela teria que
falar tudo de novo. O audio fica aqui em disco e e transcrito sozinho
assim que a conta volta.

Guarda no maximo MAX_ITEMS, descartando os mais antigos: isto nao e
arquivo morto, e so o bastante pra nao perder o que acabou de ser dito.
"""
import time

import paths
from logger import log

DIR = paths.DATA_DIR / "ditados_guardados"
MAX_ITEMS = 3


def load():
    """Caminhos dos ditados guardados, do mais ANTIGO pro mais novo --
    a ordem em que foram falados, que e a ordem de transcrever."""
    try:
        return sorted(DIR.glob("*.wav"))
    except OSError:
        return []


def count():
    return len(load())


def add(wav_bytes):
    """Guarda um ditado. Retorna quantos estao guardados agora, ou 0 se
    nao deu pra salvar (nunca levanta: perder o audio ja e ruim, derrubar
    o app junto seria pior)."""
    if not wav_bytes:
        return 0
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        agora = time.time()
        nome = "{}-{:03d}.wav".format(
            time.strftime("%Y%m%d-%H%M%S", time.localtime(agora)), int(agora % 1 * 1000))
        (DIR / nome).write_bytes(wav_bytes)
    except OSError as e:
        log(f"Nao deu pra guardar o ditado: {e}")
        return 0

    guardados = load()
    # o que acabou de ser falado e o que mais importa: quem sai e o mais antigo
    for velho in guardados[:-MAX_ITEMS]:
        remove(velho)
        log(f"Ditado guardado mais antigo descartado ({velho.name}) - limite de {MAX_ITEMS}")
    return len(load())


def remove(caminho):
    try:
        caminho.unlink(missing_ok=True)
    except OSError as e:
        log(f"Nao deu pra apagar o ditado guardado {caminho.name}: {e}")
