"""PySide6 / Qt UI for BinarySlicer."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .controller import AnalysisResult, TableRow, analyze_input
from .paths import application_dir, ensure_user_config_dir, user_config_dir
from .theme import available_themes, load_theme_document, resolve_theme, save_theme_document


@dataclass
class ThemePalette:
    """Expose theme tokens as convenience attributes."""

    bg: str
    panel: str
    panel2: str
    border: str
    text: str
    muted: str
    accent: str
    accent2: str
    info: str
    select: str
    ok: str
    warn: str
    error: str


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))


def _mix(color: str, other: str, ratio: float) -> str:
    r1, g1, b1 = _hex_to_rgb(color)
    r2, g2, b2 = _hex_to_rgb(other)
    r = int(r1 * (1 - ratio) + r2 * ratio)
    g = int(g1 * (1 - ratio) + g2 * ratio)
    b = int(b1 * (1 - ratio) + b2 * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast_color(color: str) -> str:
    r, g, b = _hex_to_rgb(color)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luma > 186 else "#ffffff"


def _build_stylesheet(tokens: ThemePalette) -> str:
    on_accent = _contrast_color(tokens.accent)
    on_ok = _contrast_color(tokens.ok)
    on_warn = _contrast_color(tokens.warn)
    on_error = _contrast_color(tokens.error)
    pill_radius = 18
    surface_radius = 14
    input_radius = 14

    return f"""
    QWidget {{
        background: {tokens.bg};
        color: {tokens.text};
        font-family: "Inter", "Segoe UI", "Noto Sans";
        font-size: 12pt;
    }}
    QFrame#panel, QFrame#toolbar, QFrame#options, QFrame#card {{
        background-color: {tokens.panel};
        border: 1px solid {tokens.border};
        border-radius: {surface_radius}px;
    }}
    QFrame#card {{
        padding: 10px;
    }}
    QFrame#summaryAccent {{
        background: {tokens.ok};
        border: none;
        border-radius: 4px;
    }}
    QLabel#mutedLabel {{
        color: {tokens.muted};
    }}
    QLabel#titleLabel {{
        font-size: 18pt;
        font-weight: 700;
        color: {tokens.text};
    }}
    QLabel#subtitleLabel {{
        color: {tokens.muted};
        font-size: 11pt;
        margin-left: 6px;
    }}
    QLineEdit {{
        background: {tokens.panel2};
        color: {tokens.text};
        border: 2px solid {tokens.border};
        border-radius: {input_radius}px;
        padding: 12px 14px;
        selection-background-color: {tokens.select};
    }}
    QLineEdit:focus {{
        border-color: {tokens.ok};
    }}
    QPushButton {{
        background-color: {tokens.panel2};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        border-radius: {pill_radius}px;
        padding: 10px 16px;
    }}
    QPushButton:hover {{
        background-color: {_mix(tokens.panel2, tokens.accent2, 0.12)};
    }}
    QPushButton:pressed {{
        background-color: {_mix(tokens.panel2, tokens.accent, 0.2)};
    }}
    QPushButton#primaryButton {{
        background-color: {tokens.accent};
        color: {on_accent};
        border: 1px solid {tokens.accent};
    }}
    QPushButton#primaryButton:hover {{
        background-color: {_mix(tokens.accent, tokens.accent2, 0.3)};
    }}
    QPushButton#primaryButton:pressed {{
        background-color: {tokens.select};
    }}
    QPushButton[chip="true"] {{
        background-color: {tokens.panel2};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        padding: 8px 14px;
    }}
    QPushButton[chip="true"]:checked {{
        background-color: {_mix(tokens.accent, tokens.panel, 0.25)};
        border-color: {tokens.accent};
    }}
    QPushButton[status="ok"] {{
        background: {tokens.ok};
        color: {on_ok};
        border: 1px solid {tokens.ok};
    }}
    QPushButton[status="warn"] {{
        background: {tokens.warn};
        color: {on_warn};
        border: 1px solid {tokens.warn};
    }}
    QPushButton[status="error"] {{
        background: {tokens.error};
        color: {on_error};
        border: 1px solid {tokens.error};
    }}
    QTabWidget::pane {{
        border: 1px solid {tokens.border};
        border-radius: {surface_radius}px;
        padding: 6px;
        background: {tokens.panel};
    }}
    QTabBar::tab {{
        background: {tokens.panel2};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        border-radius: {pill_radius}px;
        padding: 6px 14px;
        margin-right: 8px;
        margin-top: 4px;
    }}
    QTabBar::tab:selected {{
        background: {tokens.panel};
        border: 1px solid {tokens.accent};
    }}
    QTabBar::tab:hover {{
        background: {_mix(tokens.panel2, tokens.accent2, 0.1)};
    }}
    QPlainTextEdit {{
        background: {tokens.panel};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        border-radius: {surface_radius}px;
        padding: 10px;
    }}
    QSplitter::handle {{
        background: {tokens.bg};
        width: 8px;
    }}
    QTableView {{
        background: {tokens.panel};
        color: {tokens.text};
        gridline-color: {tokens.border};
        selection-background-color: {tokens.ok};
        selection-color: {_contrast_color(tokens.ok)};
        border: 1px solid {tokens.border};
        border-radius: 12px;
    }}
    QHeaderView::section {{
        background: {tokens.panel2};
        color: {tokens.text};
        padding: 6px 10px;
        border: none;
        border-right: 1px solid {tokens.border};
    }}
    """


class QtMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_user_config_dir()
        self.theme_doc = load_theme_document()
        self.theme_mode = self.theme_doc.get("last_mode", "dark_charcoal_jci")
        if self.theme_mode not in available_themes():
            self.theme_mode = "dark_charcoal_jci"
        self.tokens = ThemePalette(**resolve_theme(self.theme_mode, self.theme_doc))
        self.last_result: AnalysisResult | None = None

        self.setWindowTitle("BinarySlicer – JCI Edition")
        self.setMinimumSize(1100, 640)
        self._apply_palette()
        self._build_ui()
        self._apply_theme()

    def _apply_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(self.tokens.bg))
        palette.setColor(QPalette.WindowText, QColor(self.tokens.text))
        self.setPalette(palette)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = self._build_header()
        layout.addWidget(header)

        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        options = self._build_options_row()
        layout.addWidget(options)

        body = self._build_body()
        layout.addWidget(body, 1)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        title = QLabel("BinarySlicer")
        title.setObjectName("titleLabel")
        subtitle = QLabel("JCI Edition")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(title, 0, Qt.AlignLeft)
        layout.addWidget(subtitle, 0, Qt.AlignLeft)
        layout.addStretch(1)

        self.theme_indicator = QPushButton()
        self.theme_indicator.setFixedSize(18, 18)
        self.theme_indicator.setCheckable(True)
        self.theme_indicator.setChecked(self.theme_mode.startswith("light"))
        self.theme_indicator.setToolTip("Toggle theme")
        self.theme_indicator.clicked.connect(self.toggle_theme)
        self.theme_indicator.setObjectName("primaryButton")
        layout.addWidget(self.theme_indicator, 0, Qt.AlignRight)
        return frame

    def _build_toolbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("toolbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        label = QLabel("Input")
        label.setObjectName("mutedLabel")
        layout.addWidget(label)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("000101101000...")
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.Monospace)
        self.input_field.setFont(mono_font)
        layout.addWidget(self.input_field, 1)

        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.setObjectName("primaryButton")
        self.calculate_btn.clicked.connect(self.on_calculate)
        layout.addWidget(self.calculate_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_results)
        layout.addWidget(self.copy_btn)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_csv)
        layout.addWidget(self.export_btn)

        self.theme_btn = QPushButton("Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_btn)

        return frame

    def _build_options_row(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("options")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        label = QLabel("Options")
        label.setObjectName("mutedLabel")
        layout.addWidget(label)

        self.parity_diag_btn = QPushButton("Parity diagnostics")
        self.parity_diag_btn.setCheckable(True)
        self.parity_diag_btn.setProperty("chip", True)
        layout.addWidget(self.parity_diag_btn)

        self.auto_slice_btn = QPushButton("Auto slicing")
        self.auto_slice_btn.setCheckable(True)
        self.auto_slice_btn.setChecked(True)
        self.auto_slice_btn.setProperty("chip", True)
        layout.addWidget(self.auto_slice_btn)

        self.offset_chip = QPushButton("Offset: —")
        self.offset_chip.setEnabled(False)
        self.offset_chip.setProperty("chip", True)
        layout.addWidget(self.offset_chip)

        self.parity_status_chip = QPushButton("Parity –")
        self.parity_status_chip.setEnabled(False)
        self.parity_status_chip.setProperty("chip", True)
        self.parity_status_chip.setProperty("status", "warn")
        layout.addWidget(self.parity_status_chip)

        self.rightmost_btn = QPushButton("Rightmost")
        self.rightmost_btn.setCheckable(True)
        self.rightmost_btn.setProperty("chip", True)
        layout.addWidget(self.rightmost_btn)

        layout.addStretch(1)
        return frame

    def _build_body(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        self.summary_card = self._build_summary_card()
        splitter.addWidget(self.summary_card)

        self.tab_widget = self._build_tabs()
        splitter.addWidget(self.tab_widget)

        splitter.setSizes([400, 700])
        return splitter

    def _build_summary_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        accent = QFrame()
        accent.setObjectName("summaryAccent")
        accent.setFixedHeight(5)
        layout.addWidget(accent)

        header = QLabel("Summary")
        header.setObjectName("titleLabel")
        header.setStyleSheet("font-size: 16pt;")
        layout.addWidget(header)

        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.Monospace)
        mono_font.setPointSize(11)
        self.summary_text.setFont(mono_font)
        layout.addWidget(self.summary_text, 1)
        return card

    def _build_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)

        # Table tab
        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        table_layout.setContentsMargins(8, 8, 8, 8)
        table_layout.setSpacing(8)

        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.SingleSelection)
        self.table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_model = QStandardItemModel(0, 4, self)
        self.table_model.setHorizontalHeaderLabels(["Field", "Range", "Value", "Hex"])
        self.table_view.setModel(self.table_model)
        table_layout.addWidget(self.table_view)

        tabs.addTab(table_tab, "Table")

        # Diagnostics tab
        diag_tab = QWidget()
        diag_layout = QVBoxLayout(diag_tab)
        diag_layout.setContentsMargins(8, 8, 8, 8)
        diag_layout.setSpacing(8)

        self.diag_view = QTableView()
        self.diag_view.setSelectionBehavior(QTableView.SelectRows)
        self.diag_view.setSelectionMode(QTableView.SingleSelection)
        self.diag_view.setEditTriggers(QTableView.NoEditTriggers)
        self.diag_view.verticalHeader().setVisible(False)
        self.diag_view.horizontalHeader().setStretchLastSection(True)
        self.diag_model = QStandardItemModel(0, 8, self)
        self.diag_model.setHorizontalHeaderLabels(
            ["Type", "Coverage", "Status", "Expected", "Actual", "DataLen", "ParityBit", "Gate"]
        )
        self.diag_view.setModel(self.diag_model)
        diag_layout.addWidget(self.diag_view)

        tabs.addTab(diag_tab, "Diagnostics")
        return tabs

    def _apply_theme(self) -> None:
        self.tokens = ThemePalette(**resolve_theme(self.theme_mode, self.theme_doc))
        self._apply_palette()
        self.setStyleSheet(_build_stylesheet(self.tokens))
        self.theme_indicator.setChecked(self.theme_mode.startswith("light"))
        self._refresh_status_chips()

    def current_slice_mode(self) -> str:
        if self.auto_slice_btn.isChecked():
            return "auto"
        return "right" if self.rightmost_btn.isChecked() else "left"

    def on_calculate(self) -> None:
        result = analyze_input(
            self.input_field.text(),
            show_parity_failures=self.parity_diag_btn.isChecked(),
            slice_mode=self.current_slice_mode(),
        )
        if result.error:
            QMessageBox.warning(self, "Input error", result.error)
            return
        self.last_result = result
        self.summary_text.setPlainText(result.summary_text or "No results to display.")
        self._populate_table(result.table_rows)
        self._populate_diagnostics(result.parity_results)
        self._refresh_status_chips()

    def _populate_table(self, rows: list[TableRow]) -> None:
        self.table_model.removeRows(0, self.table_model.rowCount())
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.Monospace)
        for row in rows:
            items = [
                QStandardItem(row.field),
                QStandardItem(row.range),
                QStandardItem(row.value),
                QStandardItem(row.hex),
            ]
            items[2].setFont(mono_font)
            for item in items:
                item.setEditable(False)
            self.table_model.appendRow(items)
        self.table_view.resizeColumnsToContents()

    def _populate_diagnostics(self, parity_rows: list[dict]) -> None:
        self.diag_model.removeRows(0, self.diag_model.rowCount())
        if not parity_rows:
            return
        for entry in parity_rows:
            coverage = entry.get("coverage") or ("?", "?")
            parity_bit = entry.get("parity_bit")
            values = [
                str(entry.get("label") or entry.get("type", "")),
                f"{coverage[0]}–{coverage[1]}",
                "OK" if entry.get("ok") is True else ("FAIL" if entry.get("ok") is False else "Not evaluated"),
                str(entry.get("expected", "")),
                str(entry.get("actual", "")),
                str(entry.get("data_len", "")),
                "-" if parity_bit is None else str(parity_bit),
                "Gated" if entry.get("gate", True) else "Advisory",
            ]
            items = [QStandardItem(v) for v in values]
            for item in items:
                item.setEditable(False)
            self.diag_model.appendRow(items)
        self.diag_view.resizeColumnsToContents()

    def _refresh_status_chips(self) -> None:
        parity_status = "warn"
        parity_label = "Parity —"
        if self.last_result:
            if self.last_result.parity_ok is True:
                parity_status = "ok"
                parity_label = "Parity OK"
            elif self.last_result.parity_ok is False:
                parity_status = "error"
                parity_label = "Parity check failed"
            offset = self.last_result.offset
            if offset is not None:
                self.offset_chip.setText(f"Offset: {offset}")
            else:
                self.offset_chip.setText("Offset: —")
        self.parity_status_chip.setProperty("status", parity_status)
        self.parity_status_chip.setText(parity_label)
        self.parity_status_chip.style().unpolish(self.parity_status_chip)
        self.parity_status_chip.style().polish(self.parity_status_chip)
        self.offset_chip.style().unpolish(self.offset_chip)
        self.offset_chip.style().polish(self.offset_chip)

    def copy_results(self) -> None:
        if not self.last_result:
            QMessageBox.information(self, "Nothing to copy", "Calculate first to copy results.")
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_result.summary_text)
        QMessageBox.information(self, "Copied", "Summary copied to clipboard.")

    def export_csv(self) -> None:
        if not self.last_result or not self.last_result.table_rows:
            QMessageBox.information(self, "No data", "Please calculate first.")
            return
        default_name = f"CardExport.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(user_config_dir() / default_name), "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Field", "Range", "Value", "Hex", "Bits"])
            for row in self.last_result.table_rows:
                writer.writerow([row.field, row.range, row.value, row.hex, row.bits])
        QMessageBox.information(self, "Exported", f"CSV exported to {path}")

    def toggle_theme(self) -> None:
        modes = list(available_themes())
        next_idx = (modes.index(self.theme_mode) + 1) % len(modes)
        self.theme_mode = modes[next_idx]
        self.theme_doc["last_mode"] = self.theme_mode
        save_theme_document(self.theme_doc)
        self._apply_theme()


def main() -> None:
    app = QApplication(sys.argv)
    base_dir = getattr(sys, "_MEIPASS", application_dir())
    ico_path = Path(base_dir) / "icons" / "jci_globe.ico"
    png_path = Path(base_dir) / "icons" / "jci_globe_256.png"
    window = QtMainWindow()
    try:
        if ico_path.exists():
            window.setWindowIcon(QIcon(str(ico_path)))
        elif png_path.exists():
            window.setWindowIcon(QIcon(str(png_path)))
    except Exception:
        pass
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
