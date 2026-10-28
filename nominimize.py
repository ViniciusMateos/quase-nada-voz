"""Janela que o Windows nao consegue minimizar.

A bolinha flutuante (e o aviso preso nela) nao sao janelas normais: nao
tem botao de minimizar, nao aparecem na barra de tarefas e o app nao tem
pra onde "voltar" se elas sumirem da tela. Mas o Win+D ("mostrar area de
trabalho") e o "minimizar tudo" nao fazem essa distincao -- mandam
minimizar em TODA janela de primeiro nivel, e a bolinha ia junto. Era
isso que fazia o app parecer que morria sozinho do nada.

Os dois caminhos que o Windows usa pra minimizar sao tratados aqui:

- WM_SYSCOMMAND/SC_MINIMIZE (menu da janela, atalhos de teclado):
  engolido, a janela nem comeca a minimizar.
- ShowWindow(SW_MINIMIZE) direto, que e o que o shell usa no Win+D: nao
  da pra vetar, chega como WM_SIZE/SIZE_MINIMIZED com o estrago ja
  feito -- ai desfaz na hora. Com SW_SHOWNOACTIVATE, nunca
  SW_RESTORE/show(): restaurar normal rouba o foco de onde o usuario
  esta digitando, e a bolinha nunca pode fazer isso.
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QTimer

_WM_SYSCOMMAND = 0x0112
_WM_SIZE = 0x0005
_SC_MINIMIZE = 0xF020
_SIZE_MINIMIZED = 1
_SW_SHOWNOACTIVATE = 4


class NoMinimizeMixin:
    """Entra ANTES do QWidget na lista de bases, pra pegar o nativeEvent
    primeiro. Usa o _reassert_topmost da propria janela, se existir."""

    def nativeEvent(self, event_type, message):
        if event_type == "windows_generic_MSG":
            msg = None
            try:
                msg = wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError, OSError):
                pass
            if msg is not None:
                if msg.message == _WM_SYSCOMMAND and (msg.wParam & 0xFFF0) == _SC_MINIMIZE:
                    return True, 0
                if msg.message == _WM_SIZE and msg.wParam == _SIZE_MINIMIZED:
                    # desfazer DENTRO do handler nao funciona (o Windows
                    # ainda esta no meio da troca de estado): volta na
                    # proxima passada do loop de eventos
                    QTimer.singleShot(0, self._undo_minimize)
        return super().nativeEvent(event_type, message)

    def _undo_minimize(self):
        try:
            ctypes.windll.user32.ShowWindow(int(self.winId()), _SW_SHOWNOACTIVATE)
        except OSError:
            pass
        reassert = getattr(self, "_reassert_topmost", None)
        if reassert is not None:
            reassert()
