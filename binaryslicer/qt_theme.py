"""Qt stylesheet helpers for BinarySlicer."""

from __future__ import annotations

from typing import Dict

from .theme import available_themes, load_theme_document, resolve_theme, save_theme_document


def _contrast_color(color: str) -> str:
    color = color.lstrip("#")
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luma > 186 else "#ffffff"


def _mix(color: str, other: str, ratio: float) -> str:
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))

    def _clamp(channel: float) -> int:
        return max(0, min(255, int(channel)))

    r1, g1, b1 = _hex_to_rgb(color)
    r2, g2, b2 = _hex_to_rgb(other)
    r = _clamp(r1 * (1 - ratio) + r2 * ratio)
    g = _clamp(g1 * (1 - ratio) + g2 * ratio)
    b = _clamp(b1 * (1 - ratio) + b2 * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_qss(tokens: Dict[str, str]) -> str:
    """Return a QSS stylesheet using the provided tokens."""

    on_accent = _contrast_color(tokens.get("accent", "#0399CC"))
    on_ok = _contrast_color(tokens.get("ok", "#29B582"))
    on_panel = _contrast_color(tokens.get("panel", "#171a21"))
    on_select = _contrast_color(tokens.get("select", tokens.get("accent", "#0399CC")))
    panel_hover = _mix(tokens.get("panel2", tokens["panel"]), tokens.get("accent", "#0399CC"), 0.08)
    soft_border = _mix(tokens.get("border", "#2c2f36"), tokens.get("panel", "#171a21"), 0.6)

    style = f"""
    QWidget {{
        background-color: {tokens['bg']};
        color: {tokens['text']};
        font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
        font-size: 11pt;
    }}

    QLabel {{
        background: transparent;
    }}


    QFrame#Toolbar, QFrame#OptionsBar, QFrame#Card {{
        background: {tokens['panel']};
        border: 1px solid {tokens['border']};
        border-radius: 16px;
    }}


    QFrame#SummaryCard {{
        border-radius: 18px;
        border: 1px solid {soft_border};
        background: {tokens['panel']};
    }}

    QFrame#SummaryStrip {{
        background: {tokens['ok']};
        min-height: 6px;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
    }}

    QLabel#Heading {{
        font-size: 14pt;
        font-weight: 700;
        color: {tokens['text']};
    }}

    QLabel#Muted {{
        color: {tokens['muted']};
        font-weight: 500;
    }}

    QLabel[role="muted"] {{
        color: {tokens['muted']};
        font-weight: 600;
        font-size: 10pt;
    }}

    QLabel#ChipBadge {{
        background: {tokens['panel2']};
        color: {tokens['muted']};
        padding: 8px 12px;
        border-radius: 16px;
        border: 1px solid transparent;
        font-weight: 600;
    }}

    QLabel#StatusChip {{
        background: {tokens['ok']};
        color: {on_ok};
        padding: 8px 14px;
        border-radius: 14px;
        font-weight: 700;
        min-width: 110px;
        qproperty-alignment: AlignCenter;
    }}

    QLineEdit {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        padding: 12px 14px;
        border-radius: 16px;
        border: 2px solid {soft_border};
        selection-background-color: {tokens['select']};
        selection-color: {on_select};
    }}
    QLineEdit:focus {{
        border: 2px solid {tokens['ok']};
    }}
    QLineEdit[error="true"] {{
        border: 2px solid {tokens['error']};
    }}

    QComboBox {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        padding: 10px 12px;
        border-radius: 16px;
        border: 1px solid {soft_border};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {tokens['panel2']};
        selection-background-color: {tokens['select']};
        border: 1px solid {soft_border};
    }}

    QPushButton {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        border-radius: 16px;
        padding: 10px 16px;
        border: 1px solid {soft_border};
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {panel_hover};
    }}
    QPushButton:pressed {{
        background: {tokens['accent']};
        color: {on_accent};
        border: 1px solid {tokens['accent']};
    }}

    QPushButton#PrimaryButton {{
        background: {tokens['accent']};
        color: {on_accent};
        border: 1px solid {tokens['accent']};
        padding: 10px 20px;
    }}
    QPushButton#PrimaryButton:hover {{
        background: {tokens.get('accent2', tokens['accent'])};
    }}
    QPushButton#PrimaryButton:pressed {{
        background: {tokens.get('select', tokens['accent'])};
    }}

    QPushButton#ChipButton {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        padding: 8px 14px;
        border-radius: 18px;
        border: 1px solid {soft_border};
    }}
    QPushButton#ChipButton:checked {{
        background: {tokens['accent']};
        color: {on_accent};
        border: 1px solid {tokens['accent']};
    }}
    QPushButton#ChipButton:hover {{
        background: {panel_hover};
    }}

    QTextEdit {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        border-radius: 14px;
        border: 1px solid {soft_border};
        padding: 12px;
    }}

    
    QTabWidget::pane {{
        border: 1px solid {tokens['border']};
        border-radius: 14px;
        background: {tokens['panel']};
        padding: 8px;
        margin-top: 10px;   /* prevents tab clipping into the rounded border */
    }}

    QTabWidget::tab-bar {{
        left: 10px;
        top: 0px;
    }}

    QTabBar {{
        background: transparent;
    }}

    QTabBar::tab {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        border: 1px solid {tokens['border']};
        border-radius: 12px;
        padding: 6px 14px;
        min-height: 28px;
        margin-right: 6px;
    }}

    QTabBar::tab:selected {{
        background: {tokens['panel']};
        border: 1px solid {tokens['border']};
        color: {tokens.get('accent2', tokens['accent'])};
        font-weight: 600;
        margin-bottom: 0px;
    }}


    QTabBar::tab:hover {{
        color: {tokens.get('accent2', tokens['accent'])};
    }}


    QTableView {{
        background: {tokens['panel']};
        alternate-background-color: {tokens['panel2']};
        selection-background-color: {tokens['ok']};
        selection-color: {on_ok};
        border: none;                /* changed */
        border-radius: 12px;
        gridline-color: {tokens['border']};
    }}

   
    QTableView::item {{
        border: none;
        padding: 6px;
    }}
    
    QHeaderView::section {{
        background: {tokens['panel2']};
        color: {tokens['text']};
        border: none;
        border-bottom: 1px solid {tokens['border']};
        padding: 8px 10px;
        border-radius: 0px;
        font-weight: 600;
    }}

    QScrollBar:vertical {{
        border: none;
        background: {tokens['panel']};
        width: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens['panel2']};
        min-height: 24px;
        border-radius: 6px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """

    return style


class QtThemeManager:
    """Load, toggle, and emit QSS for Qt."""

    def __init__(self) -> None:
        self.document = load_theme_document()
        self.mode = self.document.get("last_mode", "dark_charcoal_jci")
        if self.mode not in available_themes():
            self.mode = "dark_charcoal_jci"
        self.tokens = resolve_theme(self.mode, self.document)

    def toggle(self) -> Dict[str, str]:
        modes = list(available_themes())
        next_idx = (modes.index(self.mode) + 1) % len(modes)
        self.mode = modes[next_idx]
        self.tokens = resolve_theme(self.mode, self.document)
        self.document["last_mode"] = self.mode
        save_theme_document(self.document)
        return self.tokens

    def refresh(self) -> Dict[str, str]:
        self.tokens = resolve_theme(self.mode, self.document)
        return self.tokens


__all__ = ["QtThemeManager", "build_qss"]
