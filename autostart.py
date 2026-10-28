import sys
import winreg
from pathlib import Path

import paths

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = paths.APP_ID


def _command(exe_path=None):
    """exe_path serve pra apontar pro .exe INSTALADO no momento em que o
    app ainda esta rodando da copia solta (ver installer.install)."""
    if paths.FROZEN:
        return f'"{exe_path or sys.executable}"'
    app_py = Path(__file__).parent / "app.py"
    return f'"{sys.executable}" "{app_py}"'


def current_command():
    """O comando que esta gravado hoje, ou None se nao tem nenhum.

    Diferente de is_enabled(): aqui nao importa se aponta pra ESTE .exe.
    Serve pra hora de instalar, quando o valor gravado pode apontar pra
    uma copia solta em outra pasta -- continua sendo "liga com o
    Windows", so apontando pro lugar errado."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
    except (FileNotFoundError, OSError):
        return None
    return value


def is_enabled():
    return current_command() == _command()


def set_enabled(enabled, exe_path=None):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command(exe_path))
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
