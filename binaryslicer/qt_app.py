"""PySide6 UI for BinarySlicer."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .controller import AnalysisResult, Controller, ParityRow, TableRow
from .paths import application_dir
from .qt_theme import QtThemeManager, build_qss


class PillButton(QtWidgets.QPushButton):
    """Shared button style for pill-like chips."""

    def __init__(self, text: str, *, checkable: bool = False, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setCheckable(checkable)
        self.setObjectName("ChipButton")
        self.setCursor(QtCore.Qt.PointingHandCursor)


class QtMainWindow(QtWidgets.QMainWindow):
    """Qt implementation of the BinarySlicer UI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BinarySlicer – JCI Edition")
        self.resize(1360, 820)

        self.controller = Controller()
        self.theme_manager = QtThemeManager()
        self.tokens = self.theme_manager.tokens
        self.last_result: Optional[AnalysisResult] = None
        self.mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.theme_dots: List[QtWidgets.QFrame] = []

        self._build_ui()
        self.apply_theme()
        self._load_icon()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        self.setCentralWidget(central)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("BinarySlicer · JCI Edition")
        title.setObjectName("Heading")
        header.addWidget(title)
        header.addStretch()
        header.addLayout(self._build_theme_indicators())
        layout.addLayout(header)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_options_bar())

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(12)
        self.splitter.addWidget(self._build_summary_card())
        self.splitter.addWidget(self._build_results_card())
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 4)
        layout.addWidget(self.splitter, stretch=1)

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label)

    def _build_theme_indicators(self) -> QtWidgets.QHBoxLayout:
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(6)
        for color in (self.tokens.get("ok", "#29B582"), self.tokens.get("accent", "#0399CC")):
            dot = QtWidgets.QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
            self.theme_dots.append(dot)
            layout.addWidget(dot)
        return layout

    def _build_toolbar(self) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Toolbar")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        label = QtWidgets.QLabel("Input")
        label.setObjectName("Muted")
        layout.addWidget(label)

        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setPlaceholderText("000101101000...")
        self.input_edit.setFont(self.mono_font)
        self.input_edit.returnPressed.connect(self.calculate)
        layout.addWidget(self.input_edit, stretch=1)

        self.calc_button = QtWidgets.QPushButton("Calculate")
        self.calc_button.setObjectName("PrimaryButton")
        self.calc_button.clicked.connect(self.calculate)
        layout.addWidget(self.calc_button)

        self.copy_button = QtWidgets.QPushButton("Copy")
        self.copy_button.setObjectName("ChipButton")
        self.copy_button.clicked.connect(self.copy_results)
        layout.addWidget(self.copy_button)

        self.csv_button = QtWidgets.QPushButton("Export CSV")
        self.csv_button.setObjectName("ChipButton")
        self.csv_button.clicked.connect(self.export_csv)
        layout.addWidget(self.csv_button)

        self.theme_button = QtWidgets.QPushButton("Toggle Theme")
        self.theme_button.setObjectName("ChipButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        return frame

    def _build_options_bar(self) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        frame.setObjectName("OptionsBar")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        label = QtWidgets.QLabel("Options")
        label.setObjectName("Muted")
        layout.addWidget(label)

        self.diagnostics_chip = PillButton("Parity diagnostics", checkable=True)
        layout.addWidget(self.diagnostics_chip)

        self.auto_chip = PillButton("Auto slicing", checkable=True)
        self.auto_chip.setChecked(True)
        self.left_chip = PillButton("Leftmost", checkable=True)
        self.right_chip = PillButton("Rightmost", checkable=True)

        self.slice_group = QtWidgets.QButtonGroup(self)
        for btn in (self.auto_chip, self.left_chip, self.right_chip):
            self.slice_group.addButton(btn)
        self.slice_group.setExclusive(True)

        layout.addWidget(self.auto_chip)
        layout.addWidget(self.left_chip)
        layout.addWidget(self.right_chip)

        self.offset_badge = QtWidgets.QLabel("Offset: —")
        self.offset_badge.setObjectName("ChipBadge")
        layout.addWidget(self.offset_badge)

        self.parity_status = QtWidgets.QLabel("Parity —")
        self.parity_status.setObjectName("StatusChip")
        layout.addWidget(self.parity_status)

        layout.addStretch()
        return frame

    def _build_summary_card(self) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("SummaryCard")
        vbox = QtWidgets.QVBoxLayout(card)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(8)

        strip = QtWidgets.QFrame()
        strip.setObjectName("SummaryStrip")
        vbox.addWidget(strip)

        header = QtWidgets.QLabel("Summary")
        header.setObjectName("Heading")
        vbox.addWidget(header)

        self.summary_text = QtWidgets.QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(self.mono_font)
        vbox.addWidget(self.summary_text, stretch=1)
        return card

    def _build_results_card(self) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        vbox = QtWidgets.QVBoxLayout(card)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(8)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        vbox.addWidget(self.tabs, stretch=1)

        self.table_tab = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(self.table_tab)
        table_layout.setContentsMargins(4, 4, 4, 4)
        table_layout.setSpacing(6)

        self.table_view = QtWidgets.QTableView()
        self.table_model = QtGui.QStandardItemModel(0, 4)
        self.table_model.setHorizontalHeaderLabels(["Field", "Range", "Value", "Hex"])
        self.table_view.setModel(self.table_model)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table_view.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table_view, stretch=1)

        self.tabs.addTab(self.table_tab, "Table")

        self.diagnostics_tab = QtWidgets.QWidget()
        diag_layout = QtWidgets.QVBoxLayout(self.diagnostics_tab)
        diag_layout.setContentsMargins(4, 4, 4, 4)
        diag_layout.setSpacing(6)

        self.diagnostics_view = QtWidgets.QTableView()
        self.diagnostics_model = QtGui.QStandardItemModel(0, 8)
        self.diagnostics_model.setHorizontalHeaderLabels(
            ["Type", "Coverage", "Status", "Expected", "Actual", "DataLen", "ParityBit", "Gate"]
        )
        self.diagnostics_view.setModel(self.diagnostics_model)
        self.diagnostics_view.setAlternatingRowColors(True)
        self.diagnostics_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.diagnostics_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.diagnostics_view.verticalHeader().setVisible(False)
        diag_layout.addWidget(self.diagnostics_view, stretch=1)

        self.diagnostics_text = QtWidgets.QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setFont(self.mono_font)
        diag_layout.addWidget(self.diagnostics_text, stretch=1)

        self.tabs.addTab(self.diagnostics_tab, "Diagnostics")
        return card

    def _load_icon(self) -> None:
        base_dir = getattr(sys, "_MEIPASS", application_dir())
        ico_path = Path(base_dir) / "icons" / "jci_globe.ico"
        png_path = Path(base_dir) / "icons" / "jci_globe_256.png"
        if ico_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(ico_path)))
        elif png_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(png_path)))

    # ---------------- Theme ----------------
    def apply_theme(self) -> None:
        qss = build_qss(self.tokens)
        self.setStyleSheet(qss)
        self._recolor_tables()
        for dot, color in zip(self.theme_dots, (self.tokens.get("ok", "#29B582"), self.tokens.get("accent", "#0399CC"))):
            dot.setStyleSheet(f"background: {color}; border-radius: 6px;")

    def toggle_theme(self) -> None:
        self.tokens = self.theme_manager.toggle()
        self.apply_theme()
        if self.last_result:
            self._apply_result(self.last_result)

    def _recolor_tables(self) -> None:
        palette = self.table_view.palette()
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(self.tokens.get("panel", "#171a21")))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(self.tokens.get("panel2", "#1f232d")))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(self.tokens.get("ok", "#29B582")))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        self.table_view.setPalette(palette)
        self.diagnostics_view.setPalette(palette)

    # ---------------- Actions ----------------
    def calculate(self) -> None:
        slice_mode = "auto"
        if self.left_chip.isChecked():
            slice_mode = "left"
        elif self.right_chip.isChecked():
            slice_mode = "right"

        result = self.controller.analyze_input(
            self.input_edit.text(),
            slice_mode=slice_mode,
            show_parity_failures=self.diagnostics_chip.isChecked(),
        )
        self._apply_result(result)

    def copy_results(self) -> None:
        if not self.summary_text.toPlainText():
            return
        QtGui.QGuiApplication.clipboard().setText(self.summary_text.toPlainText())
        self.status_label.setText("Summary copied to clipboard.")

    def export_csv(self) -> None:
        if not self.last_result or not self.last_result.csv_rows:
            QtWidgets.QMessageBox.information(self, "Export", "Please calculate before exporting.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export CSV", "CardExport.csv", "CSV Files (*.csv);;All Files (*.*)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["Format", "Field", "Value", "Hex", "BitLength", "Bits"],
            )
            writer.writeheader()
            writer.writerows(self.last_result.csv_rows)
        self.status_label.setText(f"CSV exported to {path}")

    # ---------------- Rendering ----------------
    def _apply_result(self, result: AnalysisResult) -> None:
        self.last_result = result if not result.error else None

        if result.error:
            self.input_edit.setProperty("error", True)
            self.input_edit.style().unpolish(self.input_edit)
            self.input_edit.style().polish(self.input_edit)
            QtWidgets.QMessageBox.critical(self, "Error", result.error)
            return

        self.input_edit.setProperty("error", False)
        self.input_edit.style().unpolish(self.input_edit)
        self.input_edit.style().polish(self.input_edit)

        self.summary_text.setPlainText(result.summary)
        self.diagnostics_text.setPlainText(result.diagnostics_text)

        self._populate_table(self.table_model, result.table_rows)
        self._populate_diagnostics(self.diagnostics_model, result.parity_rows)

        parity_text, parity_color = self._parity_status_text(result)
        self._set_status_chip(self.parity_status, parity_text, parity_color)

        offset_text = "Offset: —"
        if result.slice_mode == "auto" and result.best_offset is not None:
            offset_text = f"Offset: {result.best_offset}"
        elif result.slice_mode in {"left", "right"}:
            offset_text = f"{result.slice_mode.title()} mode"
        self.offset_badge.setText(offset_text)

        if result.formats_rendered:
            status = f"Rendered: {', '.join(result.formats_rendered)}"
        else:
            status = "No formats rendered."
        self.status_label.setText(status)

    def _populate_table(self, model: QtGui.QStandardItemModel, rows: Iterable[TableRow]) -> None:
        model.removeRows(0, model.rowCount())
        for row in rows:
            items: List[QtGui.QStandardItem] = [
                QtGui.QStandardItem(row.field),
                QtGui.QStandardItem(row.range),
                QtGui.QStandardItem(row.value),
                QtGui.QStandardItem(row.hex),
            ]
            items[2].setFont(self.mono_font)
            items[3].setFont(self.mono_font)
            for item in items:
                item.setEditable(False)
            model.appendRow(items)

    def _populate_diagnostics(self, model: QtGui.QStandardItemModel, rows: Iterable[ParityRow]) -> None:
        model.removeRows(0, model.rowCount())
        if not rows:
            rows = [ParityRow("Parity", "—", "Not evaluated", "", "", "", "-", "Yes", None)]
        for row in rows:
            items: List[QtGui.QStandardItem] = [
                QtGui.QStandardItem(row.label),
                QtGui.QStandardItem(row.coverage),
                QtGui.QStandardItem(row.status),
                QtGui.QStandardItem(row.expected),
                QtGui.QStandardItem(row.actual),
                QtGui.QStandardItem(row.data_len),
                QtGui.QStandardItem(row.parity_bit),
                QtGui.QStandardItem(row.gate),
            ]
            for item in items:
                item.setEditable(False)
            color = self._diagnostic_color(row.ok)
            for item in items:
                item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
            model.appendRow(items)

    def _diagnostic_color(self, ok: Optional[bool]) -> str:
        if ok is True:
            return self.tokens.get("ok", "#29B582")
        if ok is False:
            return self.tokens.get("error", "#E2555D")
        return self.tokens.get("muted", "#9aa0ad")

    def _parity_status_text(self, result: AnalysisResult) -> tuple[str, str]:
        if result.parity_ok is True:
            return "Parity OK", self.tokens.get("ok", "#29B582")
        if result.parity_ok is False:
            return "Parity issues", self.tokens.get("error", "#E2555D")
        return "Parity —", self.tokens.get("muted", "#9aa0ad")

    @staticmethod
    def _set_status_chip(label: QtWidgets.QLabel, text: str, color: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"background:{color}; color: white; padding: 8px 14px; border-radius: 14px; font-weight:700;")


def launch_qt() -> None:
    """Launch the Qt UI."""

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    window = QtMainWindow()
    window.show()
    sys.exit(app.exec())


__all__ = ["launch_qt", "QtMainWindow"]
