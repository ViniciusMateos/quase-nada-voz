import paths

TURQUOISE = "#14B8A6"
TURQUOISE_HOVER = "#17CDB8"
BG_PANEL = "#212128"
BG_INPUT = "#26262e"
BORDER = "#38383f"
TEXT = "#e8e8ea"
TEXT_MUTED = "#9a9aa2"

# Qt QSS url() precisa de forward slashes e path absoluto entre aspas
# pra funcionar direito, independente de qual for o cwd do processo.
CHEVRON_DOWN = (paths.ASSETS_DIR / "chevron-down.png").as_posix()
CHEVRON_UP = (paths.ASSETS_DIR / "chevron-up.png").as_posix()

FONT_STACK = "'Segoe UI', sans-serif"

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-family: {FONT_STACK};
    font-size: 13px;
}}
QDialog {{
    background-color: transparent;
}}
QMessageBox {{
    background-color: {BG_PANEL};
}}
#panel {{
    background-color: {BG_PANEL};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}
#titleBar {{
    background: transparent;
}}
#titleLabel {{
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
#closeButton {{
    background-color: transparent;
    border: none;
    border-radius: 13px;
    color: {TEXT_MUTED};
    font-size: 13px;
    padding: 0;
}}
#closeButton:hover {{
    background-color: #e5484d;
    color: white;
}}
QLabel {{
    background: transparent;
}}
QLineEdit, QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 12px;
    selection-background-color: {TURQUOISE};
    selection-color: #0a0a0a;
}}
QLineEdit:hover, QComboBox:hover {{
    border: 1px solid #48484f;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {TURQUOISE};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid {BORDER};
}}
QComboBox::down-arrow {{
    image: url("{CHEVRON_DOWN}");
    width: 10px;
    height: 10px;
    margin-right: 8px;
}}
QComboBox::down-arrow:on {{
    image: url("{CHEVRON_UP}");
}}
QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {TURQUOISE};
    selection-color: #0a0a0a;
    outline: none;
    padding: 4px;
}}
QPushButton {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 18px;
}}
QPushButton:hover {{
    border-color: {TURQUOISE};
}}
QPushButton:pressed {{
    background-color: {TURQUOISE};
    color: #0a0a0a;
}}
QPushButton#primaryButton {{
    background-color: {TURQUOISE};
    border: none;
    color: #0a0a0a;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {TURQUOISE_HOVER};
}}
QMenu {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {TURQUOISE};
    color: #0a0a0a;
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
    margin-top: 4px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 4px;
    margin-right: 18px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {TURQUOISE};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
#guideLabel {{
    color: {TEXT_MUTED};
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    font-size: 12px;
}}
#versionLabel {{
    color: {TEXT_MUTED};
    font-size: 10px;
    padding-top: 8px;
}}
#updateNotesLabel {{
    color: {TEXT_MUTED};
    font-size: 12px;
    line-height: 1.4;
}}
#updateSubtitle {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
"""
