r"""Instalacao de verdade no Windows: o app vira um programa na lista de
"Aplicativos instalados" (Configuracoes > Aplicativos, ou o antigo
"Programas e Recursos"), com nome, icone, versao, tamanho e botao de
desinstalar.

E instalacao POR USUARIO: copia o .exe pra %LOCALAPPDATA%\Programs e
registra em HKEY_CURRENT_USER. Nao precisa de admin -- e, justamente por
isso, nao mexe em nada que afete os outros usuarios da maquina.

Desinstalar funciona dos dois lados:

- Pela lista de programas, o Windows roda o proprio .exe com
  --uninstall (ver app.py). Se o app estiver aberto nesse momento, esse
  processo novo fecha o que esta rodando antes de limpar.
- De dentro do app (Configuracoes > Desinstalar), que chama uninstall()
  direto e fecha em seguida.

Um .exe nao consegue apagar a si mesmo enquanto roda, entao a pasta da
instalacao e removida por um .bat solto que espera o processo morrer
(ver _schedule_self_delete).

O Dev tem APP_ID proprio (paths.py), ou seja: aparece como outro
programa na lista e desinstala separado, sem encostar no app de verdade.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg
from ctypes import wintypes
from pathlib import Path

import autostart
import paths
from logger import log
from version import APP_VERSION

PUBLISHER = "Quase Nada Software House"
GITHUB_URL = "https://github.com/ViniciusMateos/quase-nada-voz"
INSTALL_FLAG = "--install"
UNINSTALL_FLAG = "--uninstall"
QUIET_FLAG = "--quiet"

_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{}".format(paths.APP_ID)

INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / paths.APP_ID
INSTALLED_EXE = INSTALL_DIR / "{}.exe".format(paths.APP_ID)
_START_MENU_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
SHORTCUT_PATH = _START_MENU_DIR / "{}.lnk".format(paths.APP_NAME)

# o app espera nesse evento pra fechar por conta propria quando o
# desinstalador pede (ver app.py). Matar o processo funcionaria, mas
# deixaria a pasta temporaria do PyInstaller (centenas de MB) pra tras.
QUIT_EVENT_NAME = "{}_QuitRequest_Event".format(paths.APP_ID)

_TH32CS_SNAPPROCESS = 0x00000002
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def is_registered():
    """Tem entrada na lista de programas do Windows?"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY, 0, winreg.KEY_READ):
            return True
    except OSError:
        return False


def running_from_install_dir():
    if not paths.FROZEN:
        return False
    try:
        return Path(sys.executable).resolve() == INSTALLED_EXE.resolve()
    except OSError:
        return False


def is_installed():
    return running_from_install_dir() and is_registered()


def can_install():
    """So o .exe empacotado se instala -- rodando do codigo-fonte nao
    existe um arquivo unico pra colocar na lista de programas."""
    return paths.FROZEN and not is_installed()


def _write_registry(exe_path):
    size_kb = 0
    try:
        size_kb = max(1, exe_path.stat().st_size // 1024)
    except OSError:
        pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as key:
        texts = {
            "DisplayName": paths.APP_NAME,
            "DisplayVersion": APP_VERSION,
            "Publisher": PUBLISHER,
            "DisplayIcon": "{},0".format(exe_path),
            "InstallLocation": str(exe_path.parent),
            "UninstallString": '"{}" {}'.format(exe_path, UNINSTALL_FLAG),
            "QuietUninstallString": '"{}" {} {}'.format(exe_path, UNINSTALL_FLAG, QUIET_FLAG),
            "URLInfoAbout": GITHUB_URL,
            "URLUpdateInfo": GITHUB_URL + "/releases",
        }
        for name, value in texts.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        # sem instalador separado nao existe "modificar" nem "reparar":
        # sem esses dois o Windows mostra botoes que nao levam a nada
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def _create_shortcut(exe_path):
    """Atalho no Menu Iniciar, pra achar o app pela busca do Windows.
    Falhar aqui nao invalida a instalacao -- o que faz o app existir pro
    Windows e o registro."""
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        try:
            _START_MENU_DIR.mkdir(parents=True, exist_ok=True)
            shortcut = Dispatch("WScript.Shell").CreateShortcut(str(SHORTCUT_PATH))
            shortcut.TargetPath = str(exe_path)
            shortcut.WorkingDirectory = str(exe_path.parent)
            shortcut.IconLocation = "{},0".format(exe_path)
            shortcut.Description = "{} - ditado por voz".format(paths.APP_NAME)
            shortcut.Save()
        finally:
            pythoncom.CoUninitialize()
        return True
    except Exception as e:
        log("Atalho do Menu Iniciar nao criado: {}".format(e))
        return False


def install():
    """Copia o .exe pra pasta de instalacao, registra na lista de
    programas e cria o atalho. Retorna o caminho do .exe instalado --
    quem chama decide se reabre de la."""
    if not paths.FROZEN:
        raise RuntimeError("Instalacao so funciona no .exe empacotado.")

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not running_from_install_dir():
        # o Windows nao deixa sobrescrever um .exe em execucao. Se ja tem
        # instalacao aberta (reinstalar por --install), pede pra ela
        # fechar antes de trocar o arquivo.
        if INSTALLED_EXE.exists():
            request_quit()
        shutil.copy2(Path(sys.executable), INSTALLED_EXE)

    _write_registry(INSTALLED_EXE)
    _create_shortcut(INSTALLED_EXE)
    # "iniciar com o Windows" guarda o caminho de quem ligou a opcao. Se
    # estava ligado em qualquer copia solta, o Windows continuaria
    # abrindo ELA (que nem e o programa da lista) -- repoe apontando pro
    # instalado. Nao da pra usar is_enabled() aqui: o valor gravado
    # aponta justamente pro outro .exe, entao ele diria que esta
    # desligado.
    if autostart.current_command() is not None:
        autostart.set_enabled(True, exe_path=INSTALLED_EXE)
    log("Instalado em {}".format(INSTALLED_EXE))
    return INSTALLED_EXE


def refresh_registry():
    """Mantem a versao que aparece na lista de programas igual a que esta
    rodando -- o app se atualiza sozinho trocando o .exe, sem passar por
    instalador nenhum."""
    if not is_installed():
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY, 0, winreg.KEY_READ) as key:
            registered, _ = winreg.QueryValueEx(key, "DisplayVersion")
        if registered == APP_VERSION:
            return
    except OSError:
        pass
    try:
        _write_registry(INSTALLED_EXE)
        log("Lista de programas atualizada para a versao {}".format(APP_VERSION))
    except OSError as e:
        log("Nao deu pra atualizar a lista de programas: {}".format(e))


def _schedule_self_delete():
    """Apaga a pasta da instalacao depois que este processo morrer.

    Tenta em loop porque o .exe continua travado por alguns instantes
    depois do app fechar; no fim o .bat se apaga."""
    bat = Path(os.environ["TEMP"]) / "{}_remover.bat".format(paths.APP_ID)
    linhas = [
        "@echo off",
        'set "ALVO={}"'.format(INSTALL_DIR),
        "for /l %%i in (1,1,40) do (",
        '    rmdir /s /q "%ALVO%" 2>nul',
        '    if not exist "%ALVO%" goto fim',
        "    ping -n 2 127.0.0.1 >nul",
        ")",
        ":fim",
        'del "%~f0"',
    ]
    bat.write_text("\r\n".join(linhas) + "\r\n", encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW,
        close_fds=True,
    )


def uninstall(remove_data=False):
    """Tira o app do Windows: "iniciar com o Windows", atalho do Menu
    Iniciar, entrada na lista de programas e, por ultimo, a propria pasta
    instalada.

    remove_data apaga tambem login salvo, historico e configuracoes
    (a pasta de dados em %LOCALAPPDATA%) -- sem isso, reinstalar volta
    com tudo como estava. Quem chama precisa fechar o app depois."""
    try:
        autostart.set_enabled(False)
    except OSError as e:
        log("Nao deu pra tirar do inicio do Windows: {}".format(e))

    SHORTCUT_PATH.unlink(missing_ok=True)

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    except OSError as e:
        log("Nao deu pra remover da lista de programas: {}".format(e))

    if remove_data and paths.FROZEN:
        shutil.rmtree(paths.DATA_DIR, ignore_errors=True)

    if running_from_install_dir():
        _schedule_self_delete()
    log("Desinstalado (dados removidos: {})".format(remove_data))


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def _process_table():
    """{pid: (nome do executavel, pid do pai)} de tudo que esta rodando."""
    kernel32 = ctypes.windll.kernel32
    tabela = {}
    snap = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return tabela
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        if kernel32.Process32First(snap, ctypes.byref(entry)):
            while True:
                tabela[entry.th32ProcessID] = (
                    entry.szExeFile.decode("latin-1", "replace"),
                    entry.th32ParentProcessID,
                )
                if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return tabela


def _instance_pids():
    """PIDs do app rodando, sem contar a propria arvore deste processo.

    Nao da pra ir por nome de imagem e pronto: no .exe onefile o
    bootloader do PyInstaller e um processo PAI com o MESMO nome do
    app -- derrubar o nosso deixaria a pasta temporaria dele pra tras e
    poderia matar este processo no meio do desinstalar."""
    tabela = _process_table()
    nossos = set()
    pid = os.getpid()
    for _ in range(8):
        if not pid or pid in nossos:
            break
        nossos.add(pid)
        pid = tabela.get(pid, ("", 0))[1]

    # os dois nomes: o deste .exe e o do instalado. Rodando de uma copia
    # baixada com outro nome ("QuaseNadaVoz (1).exe"), so o nome proprio
    # nao acharia a instalacao aberta.
    nomes = {Path(sys.executable).name.lower(), INSTALLED_EXE.name.lower()}
    return [p for p, (nome, _pai) in tabela.items()
            if nome.lower() in nomes and p not in nossos]


def request_quit(timeout_s=10.0):
    """Pede pro app aberto fechar sozinho e espera. Retorna True se nao
    sobrou nenhuma instancia."""
    kernel32 = ctypes.windll.kernel32
    evento = kernel32.CreateEventW(None, True, False, QUIT_EVENT_NAME)
    if not evento:
        return not _instance_pids()
    try:
        kernel32.SetEvent(evento)
        limite = time.time() + timeout_s
        while time.time() < limite:
            if not _instance_pids():
                return True
            time.sleep(0.3)
        return False
    finally:
        kernel32.CloseHandle(evento)


def kill_other_instances():
    """Garante que nao sobrou app rodando. Primeiro pede pra fechar
    direito (request_quit); quem nao atender vai no /F."""
    if not paths.FROZEN:
        return
    if request_quit():
        log("App fechou sozinho pro desinstalar")
        return
    alvos = _instance_pids()
    if not alvos:
        return
    cmd = ["taskkill", "/F"]
    for p in alvos:
        cmd += ["/PID", str(p)]
    subprocess.run(cmd, capture_output=True, creationflags=_CREATE_NO_WINDOW)
    log("Instancias fechadas pra desinstalar: {}".format(alvos))
