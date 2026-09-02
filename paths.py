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

if FROZEN:
    ASSETS_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets"
    DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "QuaseNadaVoz"
else:
    ASSETS_DIR = Path(__file__).parent / "assets"
    DATA_DIR = Path(__file__).parent

DATA_DIR.mkdir(parents=True, exist_ok=True)
