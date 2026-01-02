"""PySide6 UI for BinarySlicer."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .controller import AnalysisOptions, AnalysisResult, Controller
from .paths import application_dir


BASE_RADIUS = 12


@dataclass
class Theme:
    name: str
    tokens: Dict[str, str]


LIGHT_THEME = Theme(
    name="light",
    tokens={
        "bg": "#f5f6fb",
        "panel": "#ffffff",
        "panelAlt": "#eef0f8",
        "border": "#d9dce5",
        "text": "#1d2230",
        "muted": "#4b5364",
        "accent": "#0399CC",
        "accent2": "#00B8E0",
        "ok": "#29B582",
        "warn": "#7DBA00",
        "error": "#C43E44",
        "select": "#0554A3",
    },
)


DARK_THEME = Theme(
    name="dark",
    tokens={
        "bg": "#0f1116",
        "panel": "#171a21",
        "panelAlt": "#1f232d",
        "border": "#2b313b",
        "text": "#f3f5fa",
        "muted": "#b5bcc9",
        "accent": "#0399CC",
        "accent2": "#00B8E0",
        "ok": "#29B582",
        "warn": "#7DBA00",
        "error": "#E2555D",
        "select": "#0554A3",
    },
)


def build_stylesheet(theme: Theme) -> str:
    t = theme.tokens
    radius = BASE_RADIUS
    return f"""
        QWidget {{
            background: {t['bg']};
            color: {t['text']};
            font-family: 'Segoe UI', 'Inter', sans-serif;
            font-size: 11pt;
        }}
        QMainWindow::separator {{ background: {t['border']}; }}
        QFrame#Panel {{
            background: {t['panel']};
            border: 1px solid {t['border']};
            border-radius: {radius}px;
        }}
        QFrame#SummaryCard {{
            background: {t['panel']};
            border: 1px solid {t['border']};
            border-radius: {radius}px;
            padding-top: 8px;
        }}
        QFrame#CardHeader {{
            border: none;
            border-radius: {radius}px {radius}px 0 0;
            background: transparent;
        }}
        QLineEdit {{
            background: {t['panelAlt']};
            border: 2px solid {t['panelAlt']};
            padding: 12px 14px;
            border-radius: {radius}px;
            color: {t['text']};
            selection-background-color: {t['select']};
        }}
        QLineEdit:focus {{
            border-color: {t['ok']};
            outline: none;
        }}
        QPushButton {{
            background: {t['panelAlt']};
            border: 1px solid {t['border']};
            border-radius: {radius}px;
            padding: 10px 16px;
            color: {t['text']};
        }}
        QPushButton:hover {{
            background: {t['border']};
        }}
        QPushButton:pressed {{
            background: {t['panel']};
            border-color: {t['select']};
        }}
        QPushButton:disabled {{
            color: {t['muted']};
        }}
        QPushButton[class~="Primary"] {{
            background: {t['accent']};
            border: 1px solid {t['accent']};
            color: white;
        }}
        QPushButton[class~="Primary"]:hover {{ background: {t['accent2']}; }}
        QPushButton[class~="Primary"]:pressed {{ background: {t['select']}; }}
        QPushButton[class~="Chip"] {{
            background: {t['panelAlt']};
            border-radius: 18px;
            padding: 8px 16px;
            border: 1px solid {t['panelAlt']};
            color: {t['text']};
        }}
        QPushButton[class~="Chip"]:checked {{
            background: {t['panel']};
            border-color: {t['accent']};
        }}
        QPushButton[class~="Chip"][class~="Status"] {{
            background: {t['panel']};
            border: 1px solid {t['ok']};
            color: {t['text']};
        }}
        QPushButton[class~="Chip"][class~="Status"][class~="Good"] {{
            background: {t['ok']};
            color: white;
        }}
        QPushButton[class~="Chip"][class~="Status"][class~="Warn"] {{
            background: {t['warn']};
            color: white;
        }}
        QTabBar::tab {{
            background: {t['panelAlt']};
            border: 1px solid {t['panelAlt']};
            border-radius: 16px;
            padding: 8px 16px;
            margin: 0 4px;
            color: {t['text']};
        }}
        QTabBar::tab:selected {{
            background: {t['panel']};
            border-color: {t['accent']};
            color: {t['text']};
        }}
        QTabWidget::pane {{
            border: none;
        }}
        QTableView {{
            background: {t['panel']};
            border: 1px solid {t['border']};
            border-radius: {radius}px;
            alternate-background-color: {t['panelAlt']};
            selection-background-color: {t['ok']};
            selection-color: white;
            gridline-color: {t['border']};
        }}
        QHeaderView::section {{
            background: {t['panel']};
            color: {t['muted']};
            padding: 6px 8px;
            border: none;
        }}
        QTextEdit {{
            background: {t['panel']};
            border: 1px solid {t['border']};
            border-radius: {radius}px;
            padding: 12px;
            color: {t['text']};
            selection-background-color: {t['select']};
        }}
    """


class ChipButton(QtWidgets.QPushButton):
    def __init__(self, label: str, *, checkable: bool = True, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(label, parent=parent)
        self.setCheckable(checkable)
        self.setProperty("class", "Chip")
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setStyleSheet("")  # use global stylesheet


class PillTabWidget(QtWidgets.QTabWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setTabBarAutoHide(False)
        self.setMovable(False)
        self.setElideMode(QtCore.Qt.ElideRight)
        self.tabBar().setExpanding(False)
        self.setStyleSheet("")  # inherit


class BinarySlicerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BinarySlicer · JCI Edition (Qt)")
        self.controller = Controller()
        self.theme = DARK_THEME

        self.summary_text: QtWidgets.QTextEdit
        self.diagnostics_text: QtWidgets.QTextEdit
        self.table_model = QtGui.QStandardItemModel(0, 4)
        self.diag_model = QtGui.QStandardItemModel(0, 5)
        self._csv_rows: List[Dict[str, str | int]] = []
        self.parity_status_chip: ChipButton
        self.offset_chip: ChipButton
        self.slice_group: QtWidgets.QButtonGroup
        self.show_diag_chip: ChipButton
        self.input_field: QtWidgets.QLineEdit

        self._build_ui()
        self._apply_theme(self.theme)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        header = QtWidgets.QLabel("BinarySlicer · JCI Edition")
        header_font = QtGui.QFont("Segoe UI", 14, QtGui.QFont.Weight.Bold)
        header.setFont(header_font)
        root_layout.addWidget(header)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_options())

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_summary_card(), 2)
        body.addWidget(self._build_tab_card(), 3)
        root_layout.addLayout(body)

        self.setCentralWidget(central)
        self.resize(1400, 820)

    def _build_toolbar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Panel")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        label = QtWidgets.QLabel("Input")
        label.setStyleSheet("color: #8f96a6;")
        layout.addWidget(label)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("000101101000...")
        mono = QtGui.QFont("Cascadia Mono", 11)
        mono.setStyleHint(QtGui.QFont.Monospace)
        self.input_field.setFont(mono)
        layout.addWidget(self.input_field, 1)

        self.input_field.returnPressed.connect(self.on_calculate)

        btn_calc = QtWidgets.QPushButton("Calculate")
        btn_calc.setProperty("class", "Primary")
        btn_calc.clicked.connect(self.on_calculate)
        layout.addWidget(btn_calc)

        btn_copy = QtWidgets.QPushButton("Copy")
        btn_copy.clicked.connect(self.copy_summary)
        layout.addWidget(btn_copy)

        btn_csv = QtWidgets.QPushButton("Export CSV")
        btn_csv.clicked.connect(self.export_csv)
        layout.addWidget(btn_csv)

        btn_theme = QtWidgets.QPushButton("Toggle Theme")
        btn_theme.clicked.connect(self.toggle_theme)
        layout.addWidget(btn_theme)

        return frame

    def _build_options(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Panel")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        label = QtWidgets.QLabel("Options")
        label.setStyleSheet("color: #8f96a6;")
        layout.addWidget(label)

        self.show_diag_chip = ChipButton("Parity diagnostics", checkable=True)
        layout.addWidget(self.show_diag_chip)

        self.slice_group = QtWidgets.QButtonGroup(frame)
        self.slice_group.setExclusive(True)
        chip_auto = ChipButton("Auto slicing", checkable=True)
        chip_left = ChipButton("Leftmost", checkable=True)
        chip_right = ChipButton("Rightmost", checkable=True)
        chip_auto.setChecked(True)
        for chip in (chip_auto, chip_left, chip_right):
            self.slice_group.addButton(chip)
            layout.addWidget(chip)
        chip_auto.setProperty("sliceMode", "auto")
        chip_left.setProperty("sliceMode", "left")
        chip_right.setProperty("sliceMode", "right")

        self.parity_status_chip = ChipButton("Parity OK", checkable=False)
        self.parity_status_chip.setProperty("class", "Chip Status Good")
        layout.addWidget(self.parity_status_chip)

        self.offset_chip = ChipButton("Offset: --", checkable=False)
        self.offset_chip.setProperty("class", "Chip Status")
        layout.addWidget(self.offset_chip)

        layout.addStretch(1)
        return frame

    def _build_summary_card(self) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("SummaryCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        accent = QtWidgets.QFrame()
        accent.setFixedHeight(6)
        accent.setStyleSheet("background: #29B582; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        card_layout.addWidget(accent)

        inner = QtWidgets.QFrame()
        inner.setObjectName("Panel")
        inner_layout = QtWidgets.QVBoxLayout(inner)
        inner_layout.setContentsMargins(14, 10, 14, 14)
        inner_layout.setSpacing(10)

        title = QtWidgets.QLabel("Summary")
        title.setFont(QtGui.QFont("Segoe UI", 12, QtGui.QFont.Weight.Bold))
        inner_layout.addWidget(title)

        self.summary_text = QtWidgets.QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(QtGui.QFont("Cascadia Code", 10))
        inner_layout.addWidget(self.summary_text, 1)

        card_layout.addWidget(inner)
        return card

    def _build_tab_card(self) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("Panel")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(12)

        self.tabs = PillTabWidget()
        self.tabs.addTab(self._build_table_tab(), "Table")
        self.tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")
        card_layout.addWidget(self.tabs)
        return card

    def _build_table_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.table_view = QtWidgets.QTableView()
        headers = ["Field", "Range", "Value", "Hex"]
        self.table_model.setHorizontalHeaderLabels(headers)
        self.table_view.setModel(self.table_model)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.table_view, 1)

        return tab

    def _build_diagnostics_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.diag_view = QtWidgets.QTableView()
        headers = ["Type", "Coverage", "Status", "Expected", "Actual"]
        self.diag_model.setHorizontalHeaderLabels(headers)
        self.diag_view.setModel(self.diag_model)
        self.diag_view.setAlternatingRowColors(True)
        self.diag_view.horizontalHeader().setStretchLastSection(True)
        self.diag_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.diag_view.verticalHeader().setVisible(False)
        self.diag_view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        layout.addWidget(self.diag_view, 2)

        self.diagnostics_text = QtWidgets.QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setFont(QtGui.QFont("Cascadia Code", 10))
        self.diagnostics_text.setFixedHeight(220)
        layout.addWidget(self.diagnostics_text)
        return tab

    # ---------------------------------------------------------------- Events
    def on_calculate(self) -> None:
        opts = AnalysisOptions(
            slice_mode=self._current_slice_mode(),
            show_parity_failures=self.show_diag_chip.isChecked(),
        )
        result = self.controller.analyze_input(self.input_field.text(), options=opts)
        if not result.success:
            QtWidgets.QMessageBox.critical(self, "Error", result.error or "Unknown error")
            return
        self._render_result(result)

    def copy_summary(self) -> None:
        text = self.summary_text.toPlainText()
        QtWidgets.QApplication.clipboard().setText(text)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Summary copied")

    def export_csv(self) -> None:
        if not self.table_model.rowCount():
            QtWidgets.QMessageBox.warning(self, "Export CSV", "Please calculate first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", "CardExport.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["Format", "Field", "Value", "Hex", "BitLength", "Bits"]
                )
                writer.writeheader()
                writer.writerows(self._csv_rows)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Export CSV", f"Could not write file: {exc}")
            return
        QtWidgets.QMessageBox.information(self, "Export CSV", f"Exported to {path}")

    def toggle_theme(self) -> None:
        self.theme = LIGHT_THEME if self.theme is DARK_THEME else DARK_THEME
        self._apply_theme(self.theme)

    # ---------------------------------------------------------------- Render helpers
    def _current_slice_mode(self) -> str:
        for btn in self.slice_group.buttons():
            if btn.isChecked():
                mode = btn.property("sliceMode")
                return mode if mode else "auto"
        return "auto"

    def _render_result(self, result: AnalysisResult) -> None:
        self.summary_text.setPlainText(result.summary_text)
        self.diagnostics_text.setPlainText(result.diagnostics_text)
        self._populate_table(result)
        self._populate_diagnostics(result)
        self._update_status_chips(result)
        self._csv_rows = result.csv_rows

    def _populate_table(self, result: AnalysisResult) -> None:
        self.table_model.removeRows(0, self.table_model.rowCount())
        for row in result.table_rows:
            items = [
                QtGui.QStandardItem(str(row.field)),
                QtGui.QStandardItem(str(row.range)),
                QtGui.QStandardItem(str(row.value)),
                QtGui.QStandardItem(str(row.hex)),
            ]
            items[0].setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Weight.Medium))
            items[2].setFont(QtGui.QFont("Cascadia Mono", 10))
            items[3].setFont(QtGui.QFont("Cascadia Mono", 10))
            for item in items:
                item.setEditable(False)
            self.table_model.appendRow(items)

    def _populate_diagnostics(self, result: AnalysisResult) -> None:
        self.diag_model.removeRows(0, self.diag_model.rowCount())
        for res in result.parity_results:
            status = self._diagnostic_status(res)
            parity_bit = res.get("parity_bit")
            coverage = res.get("coverage") or ("?", "?")
            fields = [
                res.get("label") or res.get("type", ""),
                f"{coverage[0]}–{coverage[1]}",
                status,
                str(res.get("expected", "")),
                str(res.get("actual", "")),
            ]
            items = [QtGui.QStandardItem(text) for text in fields]
            for item in items:
                item.setEditable(False)
            self.diag_model.appendRow(items)

    def _update_status_chips(self, result: AnalysisResult) -> None:
        if not result.parity_results:
            self.parity_status_chip.setText("Parity n/a")
            self.parity_status_chip.setProperty("class", "Chip Status")
        else:
            gated_fail = result.parity_summary.get("gated_fail", 0)
            if gated_fail and gated_fail > 0:
                self.parity_status_chip.setText("Parity issues")
                self.parity_status_chip.setProperty("class", "Chip Status Warn")
            else:
                self.parity_status_chip.setText("Parity OK")
                self.parity_status_chip.setProperty("class", "Chip Status Good")
        self._refresh_chip_style(self.parity_status_chip)

        offset_label = "--"
        if result.rendered:
            meta = result.rendered[0].get("meta") or {}
            if meta.get("mode") == "auto":
                offset = meta.get("offset")
                if offset is not None:
                    offset_label = f"+{offset}"
        self.offset_chip.setText(f"Offset: {offset_label}")
        self._refresh_chip_style(self.offset_chip)

    def _diagnostic_status(self, result: Dict) -> str:
        ok = result.get("ok")
        gate = result.get("gate", True)
        if ok is True:
            return "OK"
        if ok is False:
            return "FAIL" if gate else "Advisory"
        return "Not evaluated"

    def _refresh_chip_style(self, chip: ChipButton) -> None:
        chip.style().unpolish(chip)
        chip.style().polish(chip)
        chip.update()

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(build_stylesheet(theme))
        palette = self.palette()
        tokens = theme.tokens
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(tokens["bg"]))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(tokens["panel"]))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(tokens["text"]))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(tokens["panelAlt"]))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(tokens["panelAlt"]))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(tokens["text"]))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(tokens["ok"]))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        self.setPalette(palette)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    base_dir = getattr(sys, "_MEIPASS", application_dir())
    ico_path = Path(base_dir) / "icons" / "jci_globe.ico"
    if ico_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(ico_path)))
    window = BinarySlicerWindow()
    window.show()
    sys.exit(app.exec())


__all__ = ["main"]
