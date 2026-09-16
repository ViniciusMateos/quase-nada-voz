"""Passo a passo guiado dentro do painel de configuracoes.

A janela escurece, so o campo da etapa atual fica iluminado (e clicavel,
da pra ir preenchendo durante o tutorial), e um cartao explica o que
fazer. As mesmas etapas alimentam a aba Tutorial -- um lugar so pra
editar o texto.
"""
from dataclasses import dataclass, field

from PySide6.QtCore import (
    Property, QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
    QRect, QRectF, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import theme


@dataclass
class TourStep:
    title: str
    text: str
    tab: str = ""                               # "", "general", "account", "history"
    targets: list = field(default_factory=list)  # nomes em SettingsDialog.tour_targets()


STEPS = [
    TourStep(
        "Bem-vindo ao Quase Nada Voz",
        "Segure uma tecla, fale e solte: o texto aparece sozinho onde o cursor estiver. "
        "Em poucos passos fica tudo configurado.",
    ),
    TourStep(
        "Sua conta do ChatGPT",
        "Coloque o email e a senha da sua conta do ChatGPT — é ela que faz a transcrição. "
        "Precisa ser login direto por senha (não pelo Google/Microsoft).",
        tab="account", targets=["email", "password"],
    ),
    TourStep(
        "Navegador do login",
        "Na primeira vez o app abre o Chrome ou o Edge sozinho pra entrar na conta. "
        "Na dúvida, deixe em Automático.",
        tab="account", targets=["browser"],
    ),
    TourStep(
        "Ative a sessão",
        "Clique em Fazer login agora. Quando der certo, o status lá em cima fica verde "
        "(Sessão ativa). Sem sessão ativa o app não deixa ditar, e a bolinha fica vermelha.",
        tab="account", targets=["login"],
    ),
    TourStep(
        "Tecla de atalho",
        "Clique aqui e aperte a tecla que você quer usar. Segure pra gravar e solte pra "
        "transcrever — ou dê um toque rápido pra deixar gravando até tocar de novo.",
        tab="general", targets=["hotkey"],
    ),
    TourStep(
        "Microfone",
        "Escolha qual microfone usar. Na dúvida, deixe o padrão do sistema.",
        tab="general", targets=["microphone"],
    ),
    TourStep(
        "Abrir com o Windows",
        "Marque pra o app já abrir sozinho quando você ligar o computador.",
        tab="general", targets=["autostart"],
    ),
    TourStep(
        "Histórico",
        "Se a colagem não pegar (acesso remoto, nenhum campo de texto em foco), as últimas "
        "transcrições ficam aqui pra você copiar.",
        tab="history", targets=["history"],
    ),
    TourStep(
        "Tudo pronto",
        "Não tem botão de salvar: tudo que você muda aqui já vale na hora. Agora é só "
        "segurar a tecla e falar — a bolinha na tela mostra quando está gravando. "
        "Pra rever este passo a passo, é só clicar neste ?.",
        tab="general", targets=["help"],
    ),
]

DIM_COLOR = QColor(6, 6, 9, 175)
SPOT_PAD = 8
SPOT_RADIUS = 12
PANEL_RADIUS = 16
# o brilho do contorno sai ate ~8px pra fora do destaque: sem essa folga
# ele era cortado quando o campo encostava na borda da janela
GLOW_MARGIN = 11
CARD_WIDTH = 300
CARD_GAP = 14
MOVE_MS = 340
FADE_MS = 180


class _Card(QWidget):
    back_clicked = Signal()
    next_clicked = Signal()
    skip_clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("tourCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(CARD_WIDTH)

        # AnimatedButton mora no settings_dialog, que importa este modulo
        from settings_dialog import AnimatedButton

        self._step_label = QLabel()
        self._step_label.setObjectName("tourStep")
        self._title = QLabel()
        self._title.setObjectName("tourTitle")
        self._title.setWordWrap(True)
        self._text = QLabel()
        self._text.setObjectName("tourText")
        self._text.setWordWrap(True)

        self._dots = QLabel()
        self._dots.setObjectName("tourDots")

        skip = QPushButton("Pular")
        skip.setObjectName("tourSkip")
        skip.setCursor(Qt.PointingHandCursor)
        skip.clicked.connect(self.skip_clicked)
        self._back = AnimatedButton("Voltar")
        self._back.clicked.connect(self.back_clicked)
        self._next = AnimatedButton("Próximo", primary=True)
        self._next.clicked.connect(self.next_clicked)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(skip)
        buttons.addStretch()
        buttons.addWidget(self._back)
        buttons.addWidget(self._next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addWidget(self._step_label)
        layout.addWidget(self._title)
        layout.addWidget(self._text)
        layout.addWidget(self._dots)
        layout.addLayout(buttons)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

    def show_step(self, index, total, step):
        self._step_label.setText(f"ETAPA {index + 1} DE {total}")
        self._title.setText(step.title)
        self._text.setText(step.text)
        dots = []
        for i in range(total):
            color = theme.TURQUOISE if i == index else ("#5a5a63" if i > index else "#2f8f84")
            dots.append(f'<span style="color:{color}">●</span>')
        self._dots.setText("&nbsp;".join(dots))
        self._back.setVisible(index > 0)
        self._next.setText("Concluir" if index == total - 1 else "Próximo")
        self.adjustSize()

    def opacity_effect(self):
        return self._opacity


class TourOverlay(QWidget):
    """Camada escura sobre o painel com um "buraco" iluminado no alvo.

    O buraco e recortado da mascara da camada, entao o clique ali cai no
    campo de verdade por baixo -- o resto do painel fica bloqueado ate o
    tutorial acabar."""

    finished = Signal(bool)  # True = concluiu, False = pulou

    def __init__(self, panel, dialog):
        super().__init__(panel)
        self._panel = panel
        self._dialog = dialog
        self._index = 0
        self._spot = QRectF()
        self._anim_group = None

        self._card = _Card(self)
        self._card.back_clicked.connect(self._back)
        self._card.next_clicked.connect(self._next)
        self._card.skip_clicked.connect(lambda: self._finish(False))

        self.setGeometry(panel.rect())
        panel.installEventFilter(self)

    # --- ciclo de vida ---------------------------------------------------

    def start(self, index=0):
        self.setGeometry(self._panel.rect())
        self.show()
        self.raise_()
        self._index = index
        self._spot = QRectF()
        self._go(index, animate=False)

    def _finish(self, completed):
        self.hide()
        self._panel.removeEventFilter(self)
        self.finished.emit(completed)
        self.deleteLater()

    def _back(self):
        if self._index > 0:
            self._go(self._index - 1)

    def _next(self):
        if self._index >= len(STEPS) - 1:
            self._finish(True)
        else:
            self._go(self._index + 1)

    # --- troca de etapa --------------------------------------------------

    def _go(self, index, animate=True):
        self._index = index
        step = STEPS[index]
        if step.tab:
            self._dialog.show_tab(step.tab)
        # a aba recem-trocada so tem geometria valida depois do layout
        # rodar: mede no proximo ciclo do event loop
        QTimer.singleShot(40, lambda: self._move_to(index, animate))

    def _target_rect(self, step):
        targets = self._dialog.tour_targets()
        widgets = []
        for name in step.targets:
            value = targets.get(name)
            widgets.extend(value if isinstance(value, (list, tuple)) else [value])
        widgets = [w for w in widgets if w is not None and w.isVisible()]
        if not widgets:
            return QRectF()
        rect = QRect()
        for w in widgets:
            top_left = w.mapTo(self._panel, QPoint(0, 0))
            rect = rect.united(QRect(top_left, w.size()))
        spot = QRectF(rect).adjusted(-SPOT_PAD, -SPOT_PAD, SPOT_PAD, SPOT_PAD)
        bounds = QRectF(self.rect()).adjusted(GLOW_MARGIN, GLOW_MARGIN, -GLOW_MARGIN, -GLOW_MARGIN)
        return spot.intersected(bounds)

    def _move_to(self, index, animate):
        if index != self._index:
            return  # usuario ja clicou de novo
        step = STEPS[index]
        target = self._target_rect(step)

        if self._anim_group is not None:
            self._anim_group.stop()

        card_fx = self._card.opacity_effect()
        if not animate:
            self.spotRect = target
            self._place_card(index, step, target)
            fade_in = QPropertyAnimation(card_fx, b"opacity", self)
            fade_in.setDuration(FADE_MS)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.start(QPropertyAnimation.DeleteWhenStopped)
            self._anim_group = None
            return

        group = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"spotRect")
        move.setDuration(MOVE_MS)
        move.setEasingCurve(QEasingCurve.InOutCubic)
        start = self._spot if not self._spot.isEmpty() else self._collapsed_at(target)
        move.setStartValue(start)
        move.setEndValue(target if not target.isEmpty() else self._collapsed_at(self._spot))
        fade_out = QPropertyAnimation(card_fx, b"opacity")
        fade_out.setDuration(FADE_MS)
        fade_out.setStartValue(card_fx.opacity())
        fade_out.setEndValue(0.0)
        group.addAnimation(move)
        group.addAnimation(fade_out)

        def arrived():
            self.spotRect = target
            self._place_card(index, step, target)
            fade_in = QPropertyAnimation(card_fx, b"opacity", self)
            fade_in.setDuration(FADE_MS)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.start(QPropertyAnimation.DeleteWhenStopped)

        group.finished.connect(arrived)
        self._anim_group = group
        group.start()

    def _collapsed_at(self, rect):
        # sem alvo (boas-vindas): o buraco "fecha" num ponto no centro
        center = rect.center() if not rect.isEmpty() else QRectF(self.rect()).center()
        return QRectF(center.x(), center.y(), 0, 0)

    def _place_card(self, index, step, target):
        self._card.show_step(index, len(STEPS), step)
        # tamanho real depois do adjustSize: o sizeHint vem mais estreito que
        # a largura fixa, e o cartao vazava pra fora da janela na borda
        size = self._card.size()
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if target.isEmpty():
            x = area.center().x() - size.width() / 2
            y = area.center().y() - size.height() / 2
        else:
            x = target.center().x() - size.width() / 2
            below = target.bottom() + CARD_GAP
            above = target.top() - CARD_GAP - size.height()
            if below + size.height() <= area.bottom():
                y = below
            elif above >= area.top():
                y = above
            else:
                y = area.bottom() - size.height()
        x = max(area.left(), min(x, area.right() - size.width()))
        y = max(area.top(), min(y, area.bottom() - size.height()))
        self._card.move(int(x), int(y))
        self._card.raise_()
        # se nao coube acima nem abaixo, o cartao fica por cima do destaque:
        # a mascara precisa devolver a area dele, senao a parte que cai no
        # buraco some (foi o que aconteceu na etapa do Historico)
        self._apply_mask()

    # --- desenho / clique atraves do buraco ---------------------------------

    def _get_spot(self):
        return self._spot

    def _set_spot(self, rect):
        self._spot = QRectF(rect)
        self._apply_mask()
        self.update()

    def _apply_mask(self):
        region = QRegion(self.rect())
        if self._spot.width() > 1 and self._spot.height() > 1:
            # buraco com os MESMOS cantos arredondados do desenho. Retangulo
            # reto cortava o neon nos cantos: o contorno arredondado passa
            # por dentro do canto do retangulo
            shape = QPainterPath()
            shape.addRoundedRect(self._spot, SPOT_RADIUS, SPOT_RADIUS)
            region = region.subtracted(QRegion(shape.toFillPolygon().toPolygon()))
        if self._card.isVisible():
            region = region.united(QRegion(self._card.geometry()))
        self.setMask(region)

    spotRect = Property(QRectF, _get_spot, _set_spot)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outer = QPainterPath()
        outer.addRoundedRect(QRectF(self.rect()), PANEL_RADIUS, PANEL_RADIUS)
        has_spot = self._spot.width() > 1 and self._spot.height() > 1
        if has_spot:
            outer.addRoundedRect(self._spot, SPOT_RADIUS, SPOT_RADIUS)
            outer.setFillRule(Qt.OddEvenFill)
        painter.fillPath(outer, DIM_COLOR)

        if has_spot:
            # contorno turquesa com um brilho suave, desenhado por FORA do
            # buraco (a mascara corta o que cair dentro)
            painter.setBrush(Qt.NoBrush)
            for grow, alpha, width in ((7, 35, 6), (4, 70, 3), (1.5, 230, 1.6)):
                color = QColor(theme.TURQUOISE)
                color.setAlpha(alpha)
                pen = QPen(color)
                pen.setWidthF(width)
                painter.setPen(pen)
                painter.drawRoundedRect(self._spot.adjusted(-grow, -grow, grow, grow),
                                        SPOT_RADIUS + grow, SPOT_RADIUS + grow)

    def mousePressEvent(self, event):
        event.accept()  # bloqueia o painel fora do buraco

    def eventFilter(self, obj, event):
        # painel mudou de tamanho (animacao de abrir, aba com altura
        # diferente): so reposiciona, sem refazer fade -- sao varios
        # resizes seguidos e o cartao ficaria piscando
        if obj is self._panel and event.type() == event.Type.Resize:
            self.setGeometry(self._panel.rect())
            QTimer.singleShot(0, self._relayout)
        return False

    def _relayout(self):
        if not self.isVisible():
            return
        if self._anim_group is not None and self._anim_group.state() == QParallelAnimationGroup.Running:
            return  # a animacao em curso ja termina no lugar certo
        step = STEPS[self._index]
        target = self._target_rect(step)
        self.spotRect = target
        self._place_card(self._index, step, target)
