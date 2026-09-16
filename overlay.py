import ctypes
import ctypes.wintypes as wintypes

from PySide6.QtCore import Qt, QObject, Signal, QRectF, QRect, QPoint, QPointF, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPainterPath, QGuiApplication, QPixmap, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

import paths
from recorder import N_BANDS

IDLE_SIZE = 36
IDLE_RADIUS = IDLE_SIZE / 2
HOVER_SIZE = 42
HOVER_RADIUS = HOVER_SIZE / 2
PROCESSING_SIZE = IDLE_SIZE + 10
PROCESSING_RADIUS = PROCESSING_SIZE / 2
ACTIVE_W, ACTIVE_H = 110, 34
ACTIVE_RADIUS = 14

# tamanho do cachorro+anel e FIXO e independente do tamanho do
# container (IDLE/HOVER/PROCESSING) -- e sempre menor que o menor
# container, pra sempre sobrar uma borda de respiro visivel.
DOG_RING_SIZE = 28

EDGE_MARGIN = 32
DOG_PATH = paths.DOG_PATH
HOVER_DEBOUNCE_MS = 40

BG_COLOR = QColor(18, 18, 22, 210)
RING_COLOR = QColor(255, 255, 255, 230)

# sessao invalida: cachorro/anel ficam vermelhos parados, e tentar ditar
# abre uma pilula vermelha com o motivo
ALERT_COLOR = QColor(239, 68, 68, 235)
ALERT_BG_COLOR = QColor(52, 14, 18, 230)
ALERT_BORDER_COLOR = QColor(239, 68, 68, 150)
ALERT_TEXT_COLOR = QColor(254, 205, 205)
MESSAGE_H = 34
MESSAGE_RADIUS = 14
MESSAGE_ICON_SIZE = 26
MESSAGE_PAD_X = 12
MESSAGE_ICON_GAP = 8
MESSAGE_FONT_PX = 12
MESSAGE_DURATION_MS = 4500
ALERT_DEFAULT_MESSAGE = "Sem login — clique para entrar"
# a pilula nasceu pra avisar erro (vermelha), mas tambem da recado bom
# -- ai ela usa o mesmo tom escuro da bolinha parada
INFO_BG_COLOR = QColor(18, 18, 22, 235)
INFO_BORDER_COLOR = QColor(255, 255, 255, 70)
INFO_TEXT_COLOR = QColor(238, 238, 242)
INFO_ICON_COLOR = QColor(245, 245, 248, 235)
RING_WIDTH = 0.9
RING_SPINNER_SPAN_DEG = 100

RESIZE_DURATION_MS = 180
BAR_SMOOTHING = 0.35
BAR_TICK_MS = 30
SPIN_TICK_MS = 20
SPIN_DEGREES_PER_TICK = 7
RING_ANIM_DURATION_MS = 220

# a sombra e desenhada a mao, em varias camadas finas seguindo o proprio
# contorno arredondado do fundo (nao um gradiente circular generico --
# isso fica errado pra formas alongadas tipo a pilula), com falloff
# exponencial. Nao da pra usar QGraphicsDropShadowEffect porque esse
# efeito, combinado com janela translucida sem moldura, corrompe as
# cores no compositor do Windows -- sai tudo acinzentado.
SHADOW_PAD = 12
SHADOW_OPACITY = 0.30
SHADOW_STEPS = 12

# o Windows as vezes derruba silenciosamente o "sempre no topo" de uma
# janela (interagir com outras janelas, DWM, sei la) -- reafirmar de
# tempos em tempos e a forma robusta de garantir que nunca fica preso
# atras de nada por muito tempo. O timer sozinho ja ajuda, mas depois
# de muitas horas rodando (principalmente atravessando desconexao/
# reconexao de RDP) ele pode simplesmente parar de disparar sem avisar
# -- por isso tambem reafirma na hora, via SetWinEventHook, toda vez
# que QUALQUER janela vira a janela em primeiro plano (e o gatilho mais
# comum de alguma coisa passar na frente da bolha).
TOPMOST_REASSERT_MS = 3000
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

_WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


class LevelBridge(QObject):
    """Emitir aqui de qualquer thread (ex: callback de audio ou a thread
    de transcricao) e o Qt entrega a atualizacao com seguranca na
    thread da GUI."""
    bands_changed = Signal(list)
    processing_done = Signal()


def _tinted_pixmap(path, size, color):
    src = QPixmap(str(path))
    if src.isNull():
        return None
    src = src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    tinted = QPixmap(src.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, src)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


class FloatingWidget(QWidget):
    """Bolinha pequena e discreta sempre visivel na tela, que o usuario
    arrasta pra onde quiser. Ociosa, mostra a logo clara sobre fundo
    escuro translucido. Passar o mouse expande um pouco (indicando que
    da pra clicar pra abrir as configuracoes). Gravando, vira uma pilula
    com um mini equalizador (niveis por faixa de frequencia, sem
    historico/scroll). Todas as trocas de tamanho sao animadas."""

    # posicao/tamanho mudou (arrastar, ou as animacoes de gravar/processar)
    # -- pra janelas "presas" na bolinha, tipo o aviso de transcricao
    geometry_changed = Signal()

    def __init__(self, initial_pos=None, on_position_changed=None, on_click=None, on_context_menu=None):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_Hover)

        self._on_position_changed = on_position_changed
        self._on_click = on_click
        self._on_context_menu = on_context_menu
        self._recording = False
        self._processing = False
        self._hovered = False
        self._drag_offset = None
        self._dragged = False
        self._target_bands = [0.0] * N_BANDS
        self._display_bands = [0.0] * N_BANDS
        self._spin_angle = 0
        self._anim = None

        # o mesmo cachorro (mesmo tamanho, mesmo pixmap, mesma posicao) e
        # usado parado e carregando -- so o anel ao redor muda -- pra
        # transicao parecer que o cachorro nem mexeu, e pra manter a
        # nitidez (reduzir um png com o circulo E o cachorro juntos
        # borra os detalhes). Um pouco maior que o anel de proposito,
        # pra encostar nele em vez de deixar uma linha de separacao.
        self._dog = _tinted_pixmap(DOG_PATH, DOG_RING_SIZE, QColor(245, 245, 248, 225))
        self._dog_alert = _tinted_pixmap(DOG_PATH, DOG_RING_SIZE, ALERT_COLOR)
        # no aviso vermelho vai a logo COMPLETA (cachorro dentro do circulo),
        # nao o cachorro solto que a bolinha usa -- ali o circulo e desenhado
        self._logo_alert = _tinted_pixmap(paths.LOGO_PATH, MESSAGE_ICON_SIZE, ALERT_COLOR)
        self._logo_info = _tinted_pixmap(paths.LOGO_PATH, MESSAGE_ICON_SIZE, INFO_ICON_COLOR)
        self._message_tone = "alert"
        self._alert = False
        self._alert_message = None
        self._message = None
        # aviso fixo (fica enquanto o mouse estiver em cima) x aviso
        # temporario (some sozinho), que nao pode ser trocado pelo hover
        self._message_persistent = False
        self._message_font = QFont(self.font())
        self._message_font.setPixelSize(MESSAGE_FONT_PX)
        self._message_font.setWeight(QFont.DemiBold)

        # o "anel" e um unico elemento que ou fecha num circulo completo
        # (parado) ou abre num arco girando (carregando) -- ringFraction
        # anima a transicao entre os dois. Nao e crossfade de opacidade
        # (isso parecia um circulo "encolhendo" de um jeito estranho,
        # ja que sao duas formas diferentes se misturando).
        self._ring_fraction = 0.0
        self._ring_anim = QPropertyAnimation(self, b"ringFraction", self)
        self._ring_anim.setDuration(RING_ANIM_DURATION_MS)
        self._ring_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._ring_anim.finished.connect(self._on_ring_anim_finished)

        self.bridge = LevelBridge()
        self.bridge.bands_changed.connect(self._on_bands)
        self.bridge.processing_done.connect(self.stop_processing)

        self._bar_timer = QTimer(self)
        self._bar_timer.timeout.connect(self._tick_bars)

        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._apply_hover_state)

        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(TOPMOST_REASSERT_MS)

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self.hide_message)

        self._set_content_size(IDLE_SIZE, IDLE_SIZE)
        self.move(*(initial_pos or self._default_pos()))
        self._clamp_to_screen()
        self.show()
        self._reassert_topmost()
        self._install_foreground_hook()

    def _reassert_topmost(self):
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
        except OSError:
            pass

    def _install_foreground_hook(self):
        # a referencia ao callback precisa ficar viva (guardada na
        # instancia) -- se o objeto ctypes for coletado pelo GC, o
        # Windows chama um ponteiro invalido e derruba o processo.
        self._foreground_hook_cb = _WinEventProcType(lambda *args: self._reassert_topmost())
        self._foreground_hook = ctypes.windll.user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            0, self._foreground_hook_cb, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        )

    def _set_content_size(self, w, h):
        self.resize(w + SHADOW_PAD * 2, h + SHADOW_PAD * 2)

    def _content_rect(self):
        return QRectF(SHADOW_PAD, SHADOW_PAD, self.width() - SHADOW_PAD * 2, self.height() - SHADOW_PAD * 2)

    def _dog_ring_rect(self, content):
        # tamanho FIXO (DOG_RING_SIZE, sempre menor que o container), so
        # recentralizado onde o fundo animado estiver -- assim o
        # cachorro/anel nao ficam "crescendo" junto quando o fundo
        # expande (hover/carregando), so sobra mais ou menos borda.
        rect = QRectF(0, 0, DOG_RING_SIZE, DOG_RING_SIZE)
        rect.moveCenter(content.center())
        return rect

    def _default_pos(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        total = IDLE_SIZE + SHADOW_PAD * 2
        return (screen.right() - total - EDGE_MARGIN, screen.bottom() - total - EDGE_MARGIN)

    def _virtual_desktop_rect(self):
        # une a area de TODOS os monitores -- so travar contra a tela
        # primaria impedia arrastar o bagulho pra outras telas.
        rect = QRect()
        for screen in QGuiApplication.screens():
            rect = rect.united(screen.availableGeometry())
        return rect

    def _clamp_to_screen(self):
        screen = self._virtual_desktop_rect()
        x = min(max(self.x(), screen.left()), screen.right() - self.width())
        y = min(max(self.y(), screen.top()), screen.bottom() - self.height())
        self.move(x, y)

    def _clamped_rect(self, rect):
        screen = self._virtual_desktop_rect()
        x = min(max(rect.x(), screen.left()), screen.right() - rect.width())
        y = min(max(rect.y(), screen.top()), screen.bottom() - rect.height())
        rect.moveTopLeft(QPoint(x, y))
        return rect

    def _animate_to(self, w, h):
        # crucial parar a animacao anterior antes de criar outra -- duas
        # QPropertyAnimation animando "geometry" ao mesmo tempo brigam
        # entre si e o resultado parece travado/duplicado.
        if self._anim is not None:
            self._anim.stop()

        center = self.geometry().center()
        target = QRect(0, 0, w + SHADOW_PAD * 2, h + SHADOW_PAD * 2)
        target.moveCenter(center)
        target = self._clamped_rect(target)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(RESIZE_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_bands(self, bands):
        self._target_bands = bands

    def _tick_bars(self):
        for i in range(N_BANDS):
            self._display_bands[i] += (self._target_bands[i] - self._display_bands[i]) * BAR_SMOOTHING
        self.update()

    def set_alert(self, active, message=None):
        """Sessao invalida: cachorro e anel ficam vermelhos parados, e passar
        o mouse abre a pilula vermelha com o motivo."""
        self._alert_message = message
        if active == self._alert:
            return
        self._alert = active
        if not active and self._message_persistent:
            self.hide_message()
        self.update()
        self._schedule_hover_check()

    def show_message(self, text, duration_ms=MESSAGE_DURATION_MS, tone="alert"):
        """Pilula vermelha com um aviso curto (ex: por que nao da pra
        ditar). Clicar nela chama on_click normalmente. duration_ms=None
        deixa fixa (usado enquanto o mouse esta em cima da bolinha)."""
        if self._recording or self._processing:
            return
        self._message_persistent = duration_ms is None
        self._message_tone = tone
        self._message = text
        self._hovered = False
        metrics = QFontMetrics(self._message_font)
        width = MESSAGE_PAD_X * 2 + MESSAGE_ICON_SIZE + MESSAGE_ICON_GAP + metrics.horizontalAdvance(text)
        self._animate_to(width, MESSAGE_H)
        if duration_ms is None:
            self._message_timer.stop()
        else:
            self._message_timer.start(duration_ms)
        self.update()

    def hide_message(self):
        if self._message is None:
            return
        self._message = None
        self._message_persistent = False
        self._message_timer.stop()
        if not self._recording and not self._processing:
            self._animate_to(IDLE_SIZE, IDLE_SIZE)
        self.update()
        # o mouse pode ter continuado em cima: deixa o hover decidir o
        # tamanho final (bolinha maior, ou a pilula de novo se for alerta)
        self._schedule_hover_check()

    def start_recording(self):
        self._message = None
        self._message_persistent = False
        self._message_timer.stop()
        self._recording = True
        self._hovered = False
        self._target_bands = [0.0] * N_BANDS
        self._display_bands = [0.0] * N_BANDS
        self._animate_to(ACTIVE_W, ACTIVE_H)
        self._bar_timer.start(BAR_TICK_MS)

    def stop_recording(self, start_processing=False):
        self._recording = False
        self._bar_timer.stop()
        if start_processing:
            self.start_processing()
        else:
            self._animate_to(IDLE_SIZE, IDLE_SIZE)
        self.update()

    def start_processing(self):
        self._processing = True
        self._spin_angle = 0
        self._spin_timer.start(SPIN_TICK_MS)
        # um pouco maior que o parado -- da mais respiro entre o anel e
        # a borda enquanto carrega, que senao fica muito colado.
        self._animate_to(PROCESSING_SIZE, PROCESSING_SIZE)
        self._animate_ring(1.0)

    def stop_processing(self):
        self._animate_to(IDLE_SIZE, IDLE_SIZE)
        self._animate_ring(0.0)

    def _animate_ring(self, target):
        self._ring_anim.stop()
        self._ring_anim.setStartValue(self._ring_fraction)
        self._ring_anim.setEndValue(target)
        self._ring_anim.start()

    def _on_ring_anim_finished(self):
        if self._ring_fraction <= 0.001:
            self._processing = False
            self._spin_timer.stop()

    def _get_ring_fraction(self):
        return self._ring_fraction

    def _set_ring_fraction(self, value):
        self._ring_fraction = value
        self.update()

    ringFraction = Property(float, _get_ring_fraction, _set_ring_fraction)

    def _tick_spin(self):
        self._spin_angle = (self._spin_angle + SPIN_DEGREES_PER_TICK) % 360
        self.update()

    def enterEvent(self, event):
        self._schedule_hover_check()

    def leaveEvent(self, event):
        self._schedule_hover_check()

    def _schedule_hover_check(self):
        # redimensionar a janela sob o cursor faz o Windows reavaliar o
        # hit-test e disparar enter/leave espurios continuamente enquanto
        # a animacao de tamanho roda. reiniciar o MESMO timer (em vez de
        # criar um QTimer.singleShot novo a cada evento) faz os eventos
        # em rajada colapsarem numa unica checagem, disparada so quando
        # a rajada realmente parar -- ou seja, so depois que o tamanho
        # ja estabilizou. Sem isso, cada evento espurio gerava sua propria
        # checagem independente e dava pra ver duas subidas seguidas.
        if self._recording or self._processing:
            return
        self._hover_timer.start(HOVER_DEBOUNCE_MS)

    def _apply_hover_state(self):
        if self._recording or self._processing:
            return
        # aviso temporario na tela (ex: tentou ditar sem login): deixa ele
        # terminar, o hover nao mexe
        if self._message is not None and not self._message_persistent:
            return

        should_hover = self.underMouse()
        if self._alert:
            # sem login: passar o mouse abre a pilula vermelha explicando
            if should_hover and not self._message_persistent:
                self._hovered = False
                self.show_message(self._alert_message or ALERT_DEFAULT_MESSAGE, duration_ms=None)
            elif not should_hover and self._message_persistent:
                self.hide_message()
            return

        if should_hover == self._hovered:
            return
        self._hovered = should_hover
        self._animate_to(HOVER_SIZE, HOVER_SIZE) if should_hover else self._animate_to(IDLE_SIZE, IDLE_SIZE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            if self._dragged:
                self._clamp_to_screen()
                if self._on_position_changed:
                    self._on_position_changed(self.x(), self.y())
            elif not self._recording and self._on_click:
                self.hide_message()
                self._on_click()
            event.accept()

    def contextMenuEvent(self, event):
        if self._on_context_menu:
            self._on_context_menu(event.globalPos())

    def moveEvent(self, event):
        super().moveEvent(event)
        self.geometry_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometry_changed.emit()

    def content_geometry(self):
        """Retangulo visivel da bolinha em coordenadas de tela (sem a
        margem transparente reservada pra sombra)."""
        return self.geometry().adjusted(SHADOW_PAD, SHADOW_PAD, -SHADOW_PAD, -SHADOW_PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        content = self._content_rect()
        if self._message:
            radius = MESSAGE_RADIUS
        elif self._recording:
            radius = ACTIVE_RADIUS
        elif self._processing:
            radius = PROCESSING_RADIUS
        elif self._hovered:
            radius = HOVER_RADIUS
        else:
            radius = IDLE_RADIUS
        self._paint_shadow(painter, content, radius)

        path = QPainterPath()
        path.addRoundedRect(content, radius, radius)

        if self._message:
            self._paint_message(painter, content, path)
            return

        painter.fillPath(path, BG_COLOR)

        if self._recording:
            self._paint_bars(painter, content)
            return

        dog_ring = self._dog_ring_rect(content)

        # vermelho so parado: carregando continua branco (a transcricao
        # ja passou pela autenticacao, o aviso de sessao nao vale ali)
        alert = self._alert and not self._processing
        dog = self._dog_alert if alert else self._dog
        if dog is not None:
            x = dog_ring.center().x() - dog.width() / 2
            y = dog_ring.center().y() - dog.height() / 2
            painter.drawPixmap(QPointF(x, y), dog)

        self._paint_ring(painter, dog_ring, alert)

    def _paint_shadow(self, painter, content, radius):
        peak_alpha = SHADOW_OPACITY * 255
        painter.setBrush(Qt.NoBrush)
        for i in range(SHADOW_STEPS, 0, -1):
            dist = i / SHADOW_STEPS
            alpha = int(peak_alpha * (1 - dist) ** 2)
            if alpha <= 0:
                continue
            rect = content.adjusted(-i, -i + 2, i, i + 2)
            pen = QPen(QColor(0, 0, 0, alpha))
            pen.setWidthF(1.5)
            painter.setPen(pen)
            path = QPainterPath()
            path.addRoundedRect(rect, radius + i, radius + i)
            painter.drawPath(path)

    def _ring_pen(self, alert=False):
        pen = QPen(ALERT_COLOR if alert else RING_COLOR)
        pen.setWidthF(RING_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        return pen

    def _ring_rect(self, dog_ring):
        inset = dog_ring.width() * 0.04
        return dog_ring.adjusted(inset, inset, -inset, -inset)

    def _paint_ring(self, painter, dog_ring, alert=False):
        # fraction 0 = circulo fechado (parado); 1 = arco de
        # RING_SPINNER_SPAN_DEG girando (carregando). anima suave entre
        # os dois em vez de cross-fade de opacidade entre duas formas
        # diferentes.
        span_deg = 360 - (360 - RING_SPINNER_SPAN_DEG) * self._ring_fraction
        painter.setPen(self._ring_pen(alert))
        painter.setBrush(Qt.NoBrush)
        start = -self._spin_angle * 16
        painter.drawArc(self._ring_rect(dog_ring), start, int(span_deg * 16))

    def _paint_message(self, painter, content, path):
        alert = self._message_tone != "info"
        painter.fillPath(path, ALERT_BG_COLOR if alert else INFO_BG_COLOR)
        border = QPen(ALERT_BORDER_COLOR if alert else INFO_BORDER_COLOR)
        border.setWidthF(1.0)
        painter.setPen(border)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        icon_x = content.left() + MESSAGE_PAD_X
        logo = self._logo_alert if alert else self._logo_info
        if logo is not None:
            icon_y = content.center().y() - logo.height() / 2
            painter.drawPixmap(QPointF(icon_x, icon_y), logo)

        text_x = icon_x + MESSAGE_ICON_SIZE + MESSAGE_ICON_GAP
        text_rect = QRectF(text_x, content.top(), content.right() - text_x - MESSAGE_PAD_X / 2, content.height())
        painter.setFont(self._message_font)
        painter.setPen(ALERT_TEXT_COLOR if alert else INFO_TEXT_COLOR)
        # durante a animacao de abrir a pilula ainda e estreita: corta com
        # "..." em vez de vazar pra fora
        metrics = QFontMetrics(self._message_font)
        shown = metrics.elidedText(self._message, Qt.ElideRight, int(max(0, text_rect.width())))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, shown)

    def _paint_bars(self, painter, content):
        gap = 5.0
        bar_w = 4.0
        total_w = N_BANDS * bar_w + (N_BANDS - 1) * gap
        start_x = content.center().x() - total_w / 2
        mid_y = content.center().y()
        max_h = content.height() * 0.62

        for i, lvl in enumerate(self._display_bands):
            h = max(3.0, lvl * max_h)
            x = start_x + i * (bar_w + gap)
            rect = QRectF(x, mid_y - h / 2, bar_w, h)
            path = QPainterPath()
            path.addRoundedRect(rect, bar_w / 2, bar_w / 2)
            painter.fillPath(path, QColor(255, 255, 255, 235))
