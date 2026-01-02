"""PySide6/Qt UI for BinarySlicer."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from .controller import AnalysisResult, BinarySlicerController, build_diagnostic_rows
from .paths import application_dir, ensure_user_config_dir, user_config_dir
from .theme import (
    available_themes,
    load_theme_document,
    resolve_theme,
    save_theme_document,
)


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


def _contrast_color(color: str) -> str:
    color = color.lstrip("#")
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luma > 186 else "#ffffff"


def build_stylesheet(tokens: dict) -> str:
    """Return a QSS stylesheet string derived from theme tokens."""
    accent = tokens.get("accent", "#0399CC")
    accent2 = tokens.get("accent2", accent)
    bg = tokens.get("bg", "#0f1116")
    panel = tokens.get("panel", bg)
    panel2 = tokens.get("panel2", panel)
    border = tokens.get("border", "#2b313b")
    text = tokens.get("text", "#f3f5fa")
    muted = tokens.get("muted", text)
    ok = tokens.get("ok", "#29B582")
    warn = tokens.get("warn", accent2)
    error = tokens.get("error", accent2)
    select = tokens.get("select", accent)
    on_accent = _contrast_color(accent)
    on_ok = _contrast_color(ok)
    on_warn = _contrast_color(warn)
    hover = _mix(accent, ok, 0.25)
    chip_radius = 16
    card_radius = 14
    tab_active = _mix(panel2, accent, 0.1)

    return f"""
    QWidget {{
        background-color: {bg};
        color: {text};
        font-family: "Inter", "Segoe UI", "Segoe UI Variable", "Arial", sans-serif;
        font-size: 11pt;
    }}
    QLabel#MutedLabel {{
        color: {muted};
        font-size: 10pt;
    }}
    QFrame#Toolbar, QFrame#OptionsBar, QFrame#Card, QFrame#TabCard {{
        background-color: {panel};
        border: 1px solid {border};
        border-radius: {card_radius}px;
    }}
    QFrame#CardAccent {{
        background-color: {ok};
        border-top-left-radius: {card_radius}px;
        border-top-right-radius: {card_radius}px;
        min-height: 4px;
        max-height: 4px;
    }}
    QLineEdit {{
        background: {panel2};
        border: 2px solid {border};
        border-radius: {chip_radius}px;
        padding: 10px;
        color: {text};
        selection-background-color: {ok};
        selection-color: {on_ok};
    }}
    QLineEdit:focus {{
        border-color: {ok};
        outline: none;
    }}
    QPushButton {{
        background: {panel2};
        color: {text};
        border: 1px solid {border};
        border-radius: {chip_radius}px;
        padding: 10px 14px;
    }}
    QPushButton:hover {{
        background: {hover};
        border-color: {accent2};
    }}
    QPushButton:pressed {{
        background: {select};
    }}
    QPushButton[variant="primary"] {{
        background: {accent};
        color: {on_accent};
        border-color: {accent};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {accent2};
    }}
    QPushButton[chip="true"] {{
        border-radius: {chip_radius + 2}px;
        padding: 8px 14px;
        background: {panel2};
    }}
    QPushButton[chip="true"][checked="true"] {{
        background: {accent};
        color: {on_accent};
        border-color: {accent};
    }}
    QPushButton[chip="true"][status="ok"] {{
        background: {ok};
        color: {on_ok};
        border-color: {ok};
    }}
    QPushButton[chip="true"][status="warn"] {{
        background: {warn};
        color: {on_warn};
        border-color: {warn};
    }}
    QPushButton[chip="true"][status="error"] {{
        background: {error};
        color: {_contrast_color(error)};
        border-color: {error};
    }}
    QPushButton[chip="true"][status="info"] {{
        background: {panel2};
        color: {text};
        border-color: {border};
    }}
    QTabWidget::pane {{
        border: 1px solid {border};
        border-radius: {card_radius}px;
        background: {panel};
        padding: 8px;
    }}
    QTabBar::tab {{
        background: {panel2};
        color: {text};
        padding: 8px 14px;
        border-radius: {chip_radius}px;
        margin-right: 6px;
    }}
    QTabBar::tab:selected {{
        background: {tab_active};
        border: 1px solid {accent};
        color: {text};
        margin-bottom: 2px;
    }}
    QTableView {{
        background: {panel};
        alternate-background-color: {_mix(panel, bg, 0.06)};
        border: 1px solid {border};
        border-radius: {card_radius}px;
        selection-background-color: {ok};
        selection-color: {on_ok};
        gridline-color: {border};
    }}
    QHeaderView::section {{
        background: {panel2};
        color: {text};
        padding: 8px 6px;
        border: none;
        border-radius: 10px;
    }}
    QTextEdit {{
        background: {panel2};
        border: 1px solid {border};
        border-radius: {card_radius}px;
        padding: 8px;
        color: {text};
    }}
    QScrollBar:vertical {{
        background: {panel2};
        width: 10px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {accent};
        min-height: 24px;
        border-radius: 4px;
    }}
    """


class PillButton(QtWidgets.QPushButton):
    def __init__(self, text: str, *, variant: str | None = None, chip: bool = False, parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        if variant:
            self.setProperty("variant", variant)
        if chip:
            self.setProperty("chip", True)


class TableModel(QtCore.QAbstractTableModel):
    HEADERS = ("Field", "Range", "Value", "Hex")

    def __init__(self, rows: Sequence = ()) -> None:
        super().__init__()
        self._rows: List = list(rows)
        self._mono = QtGui.QFont("Cascadia Code", 11)

    def update_rows(self, rows: Sequence) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return len(self.HEADERS)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == QtCore.Qt.DisplayRole:
            return (row.field, row.range, row.value, row.hex)[col]
        if role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignVCenter | (QtCore.Qt.AlignLeft if col == 0 else QtCore.Qt.AlignHCenter)
        if role == QtCore.Qt.FontRole and col >= 2:
            return self._mono
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return section + 1


class DiagnosticsModel(QtCore.QAbstractTableModel):
    HEADERS = ("Type", "Coverage", "Status", "Expected", "Actual", "DataLen", "ParityBit", "Gate")

    def __init__(self, rows: Sequence = (), tokens: dict | None = None) -> None:
        super().__init__()
        self._rows: List = list(rows)
        self._tokens = tokens or {}
        self._mono = QtGui.QFont("Cascadia Code", 11)

    def update_rows(self, rows: Sequence) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def set_tokens(self, tokens: dict) -> None:
        self._tokens = tokens or {}

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return len(self.HEADERS)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == QtCore.Qt.DisplayRole:
            return (
                row.type,
                row.coverage,
                row.status,
                row.expected,
                row.actual,
                row.data_len,
                row.parity_bit,
                row.gate,
            )[col]
        if role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignVCenter | (QtCore.Qt.AlignLeft if col == 0 else QtCore.Qt.AlignHCenter)
        if role == QtCore.Qt.FontRole and col in (2, 3, 4, 5, 6):
            return self._mono
        if role == QtCore.Qt.ForegroundRole:
            color = self._color_for_status(row.status_tag)
            return QtGui.QBrush(QtGui.QColor(color))
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return section + 1

    def _color_for_status(self, status: str) -> str:
        if status == "status_ok":
            return self._tokens.get("ok", "#29B582")
        if status == "status_fail":
            return self._tokens.get("error", "#E2555D")
        if status == "status_warn":
            return self._tokens.get("warn", "#7DBA00")
        return self._tokens.get("muted", self._tokens.get("text", "#9aa0ad"))


@dataclass
class ChipState:
    text: str
    status: str = "info"


class BinarySlicerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_user_config_dir()
        self.setWindowTitle("BinarySlicer – JCI Edition (Qt)")
        self.resize(1240, 720)

        self.controller = BinarySlicerController()
        self.theme_doc = load_theme_document()
        self.theme_mode = self.theme_doc.get("last_mode", "dark_charcoal_jci")
        if self.theme_mode not in available_themes():
            self.theme_mode = "dark_charcoal_jci"
        self.tokens = resolve_theme(self.theme_mode, self.theme_doc)
        self.slice_mode = "auto"
        self.show_parity = False
        self.current_result: AnalysisResult | None = None

        self._mono_font = QtGui.QFont("Cascadia Code", 11)
        self._body_font = QtGui.QFont("Inter", 11)

        self._build_ui()
        self._apply_theme()
        self._load_icon()

    # ---------------- UI construction ----------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        header_row = QtWidgets.QHBoxLayout()
        self.brand_label = QtWidgets.QLabel("BinarySlicer · JCI Edition")
        self.brand_label.setStyleSheet("font-size: 18pt; font-weight: 700;")
        header_row.addWidget(self.brand_label, 0, QtCore.Qt.AlignLeft)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        # Toolbar
        toolbar = QtWidgets.QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 12, 14, 12)
        toolbar_layout.setSpacing(10)

        label = QtWidgets.QLabel("Input")
        label.setObjectName("MutedLabel")
        toolbar_layout.addWidget(label)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("000101101000...")
        self.input_field.setFont(self._mono_font)
        self.input_field.returnPressed.connect(self.run_analysis)
        toolbar_layout.addWidget(self.input_field, 1)

        self.btn_calculate = PillButton("Calculate", variant="primary")
        self.btn_calculate.clicked.connect(self.run_analysis)
        toolbar_layout.addWidget(self.btn_calculate, 0)

        self.btn_copy = PillButton("Copy", chip=True)
        self.btn_copy.clicked.connect(self.copy_summary)
        toolbar_layout.addWidget(self.btn_copy, 0)

        self.btn_export = PillButton("Export CSV", chip=True)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_csv)
        toolbar_layout.addWidget(self.btn_export, 0)

        self.btn_theme = PillButton("Toggle Theme", chip=True)
        self.btn_theme.clicked.connect(self.toggle_theme)
        toolbar_layout.addWidget(self.btn_theme, 0)

        layout.addWidget(toolbar)

        # Options row
        options = QtWidgets.QFrame()
        options.setObjectName("OptionsBar")
        options_layout = QtWidgets.QHBoxLayout(options)
        options_layout.setContentsMargins(14, 8, 14, 8)
        options_layout.setSpacing(10)

        options_label = PillButton("Options", chip=True)
        options_label.setEnabled(False)
        options_layout.addWidget(options_label, 0)

        self.btn_parity = PillButton("Parity diagnostics", chip=True)
        self.btn_parity.setCheckable(True)
        self.btn_parity.clicked.connect(self._toggle_parity)
        options_layout.addWidget(self.btn_parity, 0)

        self.slice_group = QtWidgets.QButtonGroup(self)
        self.slice_group.setExclusive(True)

        self.btn_auto = PillButton("Auto slicing", chip=True)
        self.btn_auto.setCheckable(True)
        self.slice_group.addButton(self.btn_auto)
        self.btn_auto.setChecked(True)
        self.btn_auto.clicked.connect(lambda: self._set_slice_mode("auto"))
        options_layout.addWidget(self.btn_auto, 0)

        self.btn_left = PillButton("Leftmost", chip=True)
        self.btn_left.setCheckable(True)
        self.slice_group.addButton(self.btn_left)
        self.btn_left.clicked.connect(lambda: self._set_slice_mode("left"))
        options_layout.addWidget(self.btn_left, 0)

        self.btn_right = PillButton("Rightmost", chip=True)
        self.btn_right.setCheckable(True)
        self.slice_group.addButton(self.btn_right)
        self.btn_right.clicked.connect(lambda: self._set_slice_mode("right"))
        options_layout.addWidget(self.btn_right, 0)

        self.offset_chip = PillButton("Offset: —", chip=True)
        self.offset_chip.setEnabled(False)
        self.offset_chip.setProperty("status", "info")
        options_layout.addWidget(self.offset_chip, 0)

        self.parity_chip = PillButton("Parity", chip=True)
        self.parity_chip.setEnabled(False)
        self.parity_chip.setProperty("status", "warn")
        options_layout.addWidget(self.parity_chip, 0)

        options_layout.addStretch(1)
        layout.addWidget(options)

        # Main split area
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(10)

        # Summary card
        summary_card = QtWidgets.QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QtWidgets.QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(0)

        accent_bar = QtWidgets.QFrame()
        accent_bar.setObjectName("CardAccent")
        summary_layout.addWidget(accent_bar)

        summary_body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(summary_body)
        body_layout.setContentsMargins(14, 12, 14, 12)
        body_layout.setSpacing(10)

        summary_label = QtWidgets.QLabel("Summary")
        summary_label.setStyleSheet("font-size: 13pt; font-weight: 600;")
        body_layout.addWidget(summary_label)

        self.summary_text = QtWidgets.QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(self._mono_font)
        body_layout.addWidget(self.summary_text, 1)

        summary_layout.addWidget(summary_body, 1)
        splitter.addWidget(summary_card)

        # Right card with tabs
        right_card = QtWidgets.QFrame()
        right_card.setObjectName("Card")
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(10)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)

        # Table tab
        table_tab = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_tab)
        self.table_model = TableModel()
        self.table_view = QtWidgets.QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table_view.setShowGrid(False)
        self.table_view.setFont(self._body_font)
        table_layout.addWidget(self.table_view)
        tabs.addTab(table_tab, "Table")

        # Diagnostics tab
        diag_tab = QtWidgets.QWidget()
        diag_layout = QtWidgets.QVBoxLayout(diag_tab)
        self.diagnostics_model = DiagnosticsModel(tokens=self.tokens)
        self.diagnostics_view = QtWidgets.QTableView()
        self.diagnostics_view.setModel(self.diagnostics_model)
        self.diagnostics_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.diagnostics_view.verticalHeader().setVisible(False)
        self.diagnostics_view.setAlternatingRowColors(True)
        self.diagnostics_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.diagnostics_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.diagnostics_view.setShowGrid(False)
        diag_layout.addWidget(self.diagnostics_view, 2)

        self.diagnostics_report = QtWidgets.QTextEdit()
        self.diagnostics_report.setReadOnly(True)
        self.diagnostics_report.setFont(self._mono_font)
        diag_layout.addWidget(self.diagnostics_report, 1)

        tabs.addTab(diag_tab, "Diagnostics")

        right_layout.addWidget(tabs)
        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

        # Status
        self.status_label = QtWidgets.QLabel(f"Config: {user_config_dir()}")
        self.status_label.setObjectName("MutedLabel")
        layout.addWidget(self.status_label)

        self.setCentralWidget(central)

    # ---------------- Interaction ----------------
    def run_analysis(self) -> None:
        result = self.controller.analyze_input(
            self.input_field.text(),
            slice_mode=self.slice_mode,
            show_parity_failures=self.show_parity,
        )
        if result.error and not result.ok:
            QtWidgets.QMessageBox.warning(self, "BinarySlicer", result.error)
        self._apply_result(result)

    def _apply_result(self, result: AnalysisResult) -> None:
        self.current_result = result
        self.summary_text.setPlainText(result.summary or "")
        self.diagnostics_report.setPlainText(result.diagnostics_text or "")
        self.table_model.update_rows(result.table_rows)
        diag_rows = build_diagnostic_rows(result.parity_results, show_all=self.show_parity)
        self.diagnostics_model.update_rows(diag_rows)
        self._update_chips(result)
        self.btn_export.setEnabled(bool(result.csv_rows))

    def _update_chips(self, result: AnalysisResult) -> None:
        offset = result.meta.offset_used
        chip_offset = ChipState(f"Offset: {offset if offset is not None else '—'}", status="info")
        parity_status = "ok" if result.meta.parity_ok else "warn"
        parity_text = "Parity OK" if result.meta.parity_ok else "Parity check"
        chip_parity = ChipState(parity_text, status=parity_status)
        self._apply_chip_state(self.offset_chip, chip_offset)
        self._apply_chip_state(self.parity_chip, chip_parity)

    def _apply_chip_state(self, button: QtWidgets.QPushButton, state: ChipState) -> None:
        button.setText(state.text)
        button.setProperty("status", state.status)
        button.style().unpolish(button)
        button.style().polish(button)

    def copy_summary(self) -> None:
        text = self.summary_text.toPlainText()
        if not text:
            return
        QtWidgets.QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Summary copied to clipboard.", 3000)

    def export_csv(self) -> None:
        if not self.current_result or not self.current_result.csv_rows:
            QtWidgets.QMessageBox.information(self, "BinarySlicer", "Please calculate first.")
            return
        default_name = "CardExport.csv"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["Format", "Field", "Value", "Hex", "BitLength", "Bits"],
                )
                writer.writeheader()
                writer.writerows(self.current_result.csv_rows)
        except OSError as exc:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.critical(self, "BinarySlicer", f"Could not save CSV:\n{exc}")
            return
        self.statusBar().showMessage(f"CSV exported to {path}", 4000)

    def toggle_theme(self) -> None:
        modes = list(available_themes())
        next_idx = (modes.index(self.theme_mode) + 1) % len(modes)
        self.theme_mode = modes[next_idx]
        self.tokens = resolve_theme(self.theme_mode, self.theme_doc)
        self.theme_doc["last_mode"] = self.theme_mode
        save_theme_document(self.theme_doc)
        self._apply_theme()

    def _apply_theme(self) -> None:
        stylesheet = build_stylesheet(self.tokens)
        self.setStyleSheet(stylesheet)
        self.diagnostics_model.set_tokens(self.tokens)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(self.tokens.get("bg", "#0f1116")))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(self.tokens.get("text", "#f3f5fa")))
        self.setPalette(palette)

    def _set_slice_mode(self, mode: str) -> None:
        self.slice_mode = mode
        with QtCore.QSignalBlocker(self.btn_auto), QtCore.QSignalBlocker(self.btn_left), QtCore.QSignalBlocker(
            self.btn_right
        ):
            self.btn_auto.setChecked(mode == "auto")
            self.btn_left.setChecked(mode == "left")
            self.btn_right.setChecked(mode == "right")

    def _toggle_parity(self) -> None:
        self.show_parity = self.btn_parity.isChecked()
        if self.current_result:
            diag_rows = build_diagnostic_rows(self.current_result.parity_results, show_all=self.show_parity)
            self.diagnostics_model.update_rows(diag_rows)

    def _load_icon(self) -> None:
        base_dir = getattr(sys, "_MEIPASS", application_dir())
        ico_path = Path(base_dir) / "icons" / "jci_globe.ico"
        png_path = Path(base_dir) / "icons" / "jci_globe_256.png"
        if ico_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(ico_path)))
        elif png_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(png_path)))


def main() -> None:
    ensure_user_config_dir()
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    window = BinarySlicerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    main()
