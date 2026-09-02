import sys
import winreg
from pathlib import Path

import paths

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "QuaseNadaVoz"


def _command():
    if paths.FROZEN:
        return f'"{sys.executable}"'
    app_py = Path(__file__).parent / "app.py"
    return f'"{sys.executable}" "{app_py}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
    except (FileNotFoundError, OSError):
        return False
    return value == _command()


def set_enabled(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
