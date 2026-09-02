import os
import subprocess
import sys
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

import paths
from version import APP_VERSION

GITHUB_REPO = "ViniciusMateos/quase-nada-voz"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


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


def check_for_update(timeout=10):
    """Consulta a ultima release publica no GitHub. Retorna um dict com
    versao/notas/link de download se tiver uma versao mais nova que a
    instalada, ou None se nao tiver (ou se a checagem falhar -- checar
    atualizacao nunca pode impedir o app de abrir normalmente)."""
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


def download_update(download_url, timeout=60):
    """Baixa o novo .exe pra uma pasta temporaria dentro do DATA_DIR.
    Levanta excecao se falhar -- quem chama decide o que mostrar."""
    dest = paths.DATA_DIR / "update" / "QuaseNadaVoz_novo.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(download_url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    return dest


def apply_update_and_restart(new_exe_path):
    """Troca o .exe em execucao pelo novo e reabre o app. So faz sentido
    rodando empacotado (sys.executable e o proprio .exe nesse caso) --
    rodando do codigo-fonte nao ha o que substituir.

    O Windows nao deixa sobrescrever um .exe enquanto ele esta rodando,
    entao a troca precisa acontecer DEPOIS que esse processo fechar: um
    script .bat descartavel espera o PID sumir, move o novo .exe por
    cima do antigo e abre de novo."""
    if not paths.FROZEN:
        raise RuntimeError("Atualização automática só funciona no .exe empacotado.")

    current_exe = Path(sys.executable)
    pid = os.getpid()
    bat_path = paths.DATA_DIR / "update" / "aplicar_update.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    bat_content = (
        "@echo off\r\n"
        ":esperando\r\n"
        f'tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL\r\n'
        "if not errorlevel 1 (\r\n"
        "    timeout /t 1 /nobreak >NUL\r\n"
        "    goto esperando\r\n"
        ")\r\n"
        f'move /y "{new_exe_path}" "{current_exe}" >NUL\r\n'
        f'start "" "{current_exe}"\r\n'
        'del "%~f0"\r\n'
    )
    bat_path.write_text(bat_content, encoding="utf-8")

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


class UpdateCheckThread(QThread):
    found = Signal(dict)

    def run(self):
        info = check_for_update()
        if info:
            self.found.emit(info)


class UpdateDownloadThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, download_url, parent=None):
        super().__init__(parent)
        self._url = download_url

    def run(self):
        try:
            path = download_update(self._url)
            self.done.emit(str(path))
        except Exception as e:
            self.failed.emit(str(e))
