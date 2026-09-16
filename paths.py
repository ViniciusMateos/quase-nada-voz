import os
import sys
from pathlib import Path

# Rodando do codigo-fonte: tudo (recursos e dados do usuario) fica do
# lado dos arquivos .py, como sempre foi.
#
# Rodando empacotado (PyInstaller, --onefile): sys.frozen fica True e
# os recursos empacotados (assets/) sao extraidos num diretorio
# TEMPORARIO a cada execucao (sys._MEIPASS) -- ok pra coisa read-only,
# mas dados do usuario (.env, sessao salva, log) NAO PODEM morar la,
# senao somem toda vez que o app fecha. Esses vao pro %LOCALAPPDATA%,
# que e estavel entre execucoes e nao precisa de permissao de admin.
FROZEN = getattr(sys, "frozen", False)
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if FROZEN else Path(__file__).parent


def _read_channel():
    # "dev" = build de testes, instalado lado a lado com o app normal.
    # Empacotado: o build.py grava channel.txt dentro do .exe. Rodando do
    # codigo-fonte: variavel de ambiente QNV_CHANNEL=dev.
    marker = _BUNDLE_DIR / "channel.txt"
    if FROZEN and marker.exists():
        return marker.read_text(encoding="utf-8").strip() or "prod"
    return os.environ.get("QNV_CHANNEL", "prod").strip() or "prod"


CHANNEL = _read_channel()
IS_DEV = CHANNEL == "dev"

# tudo que identifica o app pro Windows e pro usuario muda no dev, pra
# os dois conviverem sem um pisar no outro: nome, icone, pasta de dados
# (login/historico/config separados), registro do "iniciar com o
# Windows" e trava de instancia unica.
APP_NAME = "Quase Nada Voz Dev" if IS_DEV else "Quase Nada Voz"
APP_ID = "QuaseNadaVozDev" if IS_DEV else "QuaseNadaVoz"

ASSETS_DIR = _BUNDLE_DIR / "assets"
ICON_PATH = ASSETS_DIR / ("icon-dev.ico" if IS_DEV else "icon.ico")
# a bolinha flutuante usa o cachorro com as ferramentas no Dev, pra dar
# pra diferenciar dos dois rodando lado a lado
DOG_PATH = ASSETS_DIR / ("dog-dev.png" if IS_DEV else "dog.png")
# logo completa (cachorro DENTRO do circulo), usada no aviso vermelho
LOGO_PATH = ASSETS_DIR / ("logo-dev.png" if IS_DEV else "logo.png")

if FROZEN:
    DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / APP_ID
elif IS_DEV:
    DATA_DIR = Path(__file__).parent / ".dev-data"
else:
    DATA_DIR = Path(__file__).parent

DATA_DIR.mkdir(parents=True, exist_ok=True)
