import threading

from PySide6.QtCore import QObject, QTimer, Signal

import auth
from logger import log

OK = auth.SESSION_OK
EXPIRED = auth.SESSION_EXPIRED
NO_CREDENTIALS = auth.SESSION_NO_CREDENTIALS
OFFLINE = auth.SESSION_OFFLINE
UNKNOWN = "unknown"

RECHECK_INTERVAL_MS = 10 * 60 * 1000

MESSAGES = {
    OK: "Sessão ativa",
    EXPIRED: "Sessão expirada",
    NO_CREDENTIALS: "Nenhuma conta configurada",
    OFFLINE: "Sem conexão com o ChatGPT",
    UNKNOWN: "Verificando sessão...",
}


class SessionMonitor(QObject):
    """Mantem o status da conta atualizado sem nunca abrir navegador:
    checa ao abrir o app, a cada 10 minutos e quando alguem pede (salvou
    a conta, testou login, uma transcricao falhou por autenticacao).

    So "expired" e "no_credentials" bloqueiam o ditado. "offline" nao
    prova nada sobre a conta, e na duvida ("unknown") deixa tentar."""

    status_changed = Signal(str)
    check_started = Signal()
    _result = Signal(str)   # fim de uma checagem
    _marked = Signal(str)   # status descoberto fora dela

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = UNKNOWN
        self._checking = False
        self._lock = threading.Lock()
        self._result.connect(self._on_check_finished)
        self._marked.connect(self._set_status)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(RECHECK_INTERVAL_MS)

    @property
    def blocked(self):
        return self.status in (EXPIRED, NO_CREDENTIALS)

    @property
    def checking(self):
        return self._checking

    def check(self):
        with self._lock:
            if self._checking:
                return
            self._checking = True
        self.check_started.emit()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result = auth.check_session()
        except Exception as e:
            log(f"Falha ao checar a sessao: {e}")
            result = OFFLINE
        self._result.emit(result)

    def _on_check_finished(self, result):
        with self._lock:
            self._checking = False
        self._set_status(result)

    def _set_status(self, result):
        changed = result != self.status
        self.status = result
        if changed:
            log(f"Sessao: {result}")
        # emite sempre: quem pediu a checagem precisa saber que terminou
        self.status_changed.emit(result)

    def mark(self, result):
        """Registra um status descoberto fora da checagem (ex: a
        transcricao nao conseguiu autenticar). Pode ser chamado de
        qualquer thread -- o sinal entrega na thread do Qt."""
        self._marked.emit(result)
