import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

import paths
from logger import log
from version import APP_VERSION

GITHUB_REPO = "ViniciusMateos/quase-nada-voz"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# a versao nova e aberta com esse argumento (com a versao antiga junto,
# "--after-update=1.1.1"): sabe que precisa esperar a antiga terminar de
# fechar e consegue avisar na tela de qual versao pra qual veio
AFTER_UPDATE_FLAG = "--after-update"


def previous_version_from_args(argv):
    """Versao de onde o app acabou de vir, ou None se nao foi
    atualizacao. Aceita o formato antigo (flag sem valor)."""
    for arg in argv:
        if arg == AFTER_UPDATE_FLAG:
            return ""
        if arg.startswith(AFTER_UPDATE_FLAG + "="):
            return arg.split("=", 1)[1]
    return None

# o Dev nunca olha as Releases (baixaria o app normal por cima dele). Pra
# testar o fluxo de atualizacao nele, basta criar esse arquivo na pasta de
# dados do Dev: {"version": "9.9.9", "notes": "...", "file": "C:\\...\\novo.exe"}
DEV_FEED_FILE = paths.DATA_DIR / "update_feed.json"

_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def _parse_version(v):
    """'v1.2.3' ou '1.2.3' -> (1, 2, 3), pra comparar sem depender de string."""
    v = v.lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def updates_enabled():
    if not paths.FROZEN:
        return False
    return DEV_FEED_FILE.exists() if paths.IS_DEV else True


def _check_dev_feed():
    try:
        data = json.loads(DEV_FEED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = str(data.get("version", ""))
    source = data.get("file")
    if not version or not source or _parse_version(version) <= _parse_version(APP_VERSION):
        return None
    return {"version": version, "notes": data.get("notes", "") or "", "download_url": source}


def check_for_update(timeout=10):
    """Retorna um dict com versao/notas/origem se tiver versao mais nova
    que a instalada, ou None (inclusive se a checagem falhar -- checar
    atualizacao nunca pode impedir o app de abrir normalmente)."""
    if paths.IS_DEV:
        return _check_dev_feed()
    try:
        resp = requests.get(
            LATEST_RELEASE_URL, timeout=timeout, headers={"Accept": "application/vnd.github+json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        latest = data.get("tag_name", "")
        if not latest or _parse_version(latest) <= _parse_version(APP_VERSION):
            return None
        asset_url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(".exe"):
                asset_url = asset.get("browser_download_url")
                break
        if not asset_url:
            return None
        return {"version": latest, "notes": data.get("body", "") or "", "download_url": asset_url}
    except (requests.RequestException, ValueError):
        return None


def download_update(source, on_progress=None, timeout=60):
    """Baixa (ou copia, no feed de teste do Dev) o novo .exe pra pasta de
    dados. on_progress(0..100) quando da pra saber o tamanho. Levanta
    excecao se falhar -- quem chama decide o que mostrar."""
    dest = paths.DATA_DIR / "update" / f"{paths.APP_ID}_novo.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")

    if not str(source).lower().startswith(("http://", "https://")):
        shutil.copyfile(source, partial)
        if on_progress:
            on_progress(100)
    else:
        with requests.get(source, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            last_pct = -1
            with open(partial, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total and on_progress:
                        pct = min(100, done * 100 // total)
                        if pct != last_pct:
                            last_pct = pct
                            on_progress(pct)
    # so vira o arquivo "de verdade" se o download terminou inteiro
    partial.replace(dest)
    return dest


def _clean_launch_env():
    """Ambiente pra abrir OUTRO .exe do PyInstaller a partir deste.

    O .exe empacotado roda com variaveis internas do PyInstaller
    (_PYI_APPLICATION_HOME_DIR, _PYI_PARENT_PROCESS_LEVEL...). Herdadas, o
    .exe novo acha que e um subprocesso DESTE e tenta rodar da pasta
    temporaria deste -- que e apagada quando este fecha, e ele morre sem
    aparecer nada. Esse era o bug de "atualiza, fecha e nao volta"."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("_PYI_")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def launch(exe_path, args=()):
    """Abre outro .exe empacotado a partir deste, com o ambiente limpo
    (ver _clean_launch_env) e solto deste processo."""
    return subprocess.Popen(
        [str(exe_path), *args],
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        env=_clean_launch_env(),
    )


def apply_update_and_restart(new_exe_path):
    """Poe o .exe novo no lugar do atual e abre ele. So faz sentido
    rodando empacotado.

    Nao da pra sobrescrever um .exe em execucao, mas da pra RENOMEAR:
    o atual vira .old, o novo assume o nome original, e ele e aberto
    direto, com o ambiente limpo (ver _clean_launch_env). A versao nova espera esta
    fechar antes de subir (AFTER_UPDATE_FLAG) e apaga o .old. Se algo
    falhar no caminho, desfaz e o app atual continua como estava."""
    if not paths.FROZEN:
        raise RuntimeError("Atualização automática só funciona no .exe empacotado.")

    current = Path(sys.executable)
    new = Path(new_exe_path)
    old = current.with_name(f"{current.name}.old-{int(time.time())}")

    current.replace(old)
    try:
        shutil.move(str(new), str(current))
    except Exception:
        old.replace(current)
        raise

    try:
        launch(current, [f"{AFTER_UPDATE_FLAG}={APP_VERSION}"])
    except Exception:
        try:
            current.replace(new)
            old.replace(current)
        except OSError:
            pass
        raise

    if paths.IS_DEV:
        # feed de teste consumido: senao a "versao nova" (que no teste e o
        # mesmo .exe) pediria pra atualizar de novo pra sempre
        DEV_FEED_FILE.unlink(missing_ok=True)
    log(f"Atualizacao aplicada, reabrindo: {current}")


def cleanup_old_executables(retries=40, interval_s=0.5):
    """Apaga sobras .old de atualizacoes anteriores. O processo antigo
    pode levar uns segundos pra soltar o arquivo, entao tenta de novo em
    segundo plano."""
    if not paths.FROZEN:
        return
    current = Path(sys.executable)

    def run():
        for _ in range(retries):
            leftovers = list(current.parent.glob(f"{current.name}.old-*"))
            if not leftovers:
                return
            for f in leftovers:
                try:
                    f.unlink()
                except OSError:
                    pass
            time.sleep(interval_s)

    threading.Thread(target=run, daemon=True).start()


class UpdateCheckThread(QThread):
    found = Signal(dict)

    def run(self):
        info = check_for_update()
        if info:
            self.found.emit(info)


class UpdateDownloadThread(QThread):
    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, download_url, parent=None):
        super().__init__(parent)
        self._url = download_url

    def run(self):
        try:
            path = download_update(self._url, on_progress=self.progress.emit)
            self.done.emit(str(path))
        except Exception as e:
            self.failed.emit(str(e))
