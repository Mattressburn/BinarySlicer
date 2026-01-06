"""Tkinter UI for BinarySlicer."""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap import ttk

from .diagnostics import build_diagnostics_report
from .decoder import format_binary_groups, process_input
from .formats import (
    FormatValidationError,
    FormatRepository,
    NormalizedFormat,
    extract_fields,
    find_best_offsets,
    normalize_format_entry,
    validate_format_entry,
    verify_parity,
    parity_score,
)
from .paths import application_dir, ensure_user_config_dir, user_config_dir
from .theme import (
    apply_bootstrap_theme,
    available_themes,
    load_theme_document,
    resolve_theme,
    save_theme_document,
)

BIT_RE = re.compile(r"^[01]+$")


class App:
    """Main BinarySlicer application."""

    def __init__(self, root: tb.Window) -> None:
        self.root = root
        self.root.title("BinarySlicer – JCI Edition")

        ensure_user_config_dir()

        # Theme
        self.theme_doc = load_theme_document()
        self.theme_mode = self.theme_doc.get("last_mode", "light_jci")
        if self.theme_mode not in available_themes():
            self.theme_mode = "light_jci"
        self.theme = resolve_theme(self.theme_mode, self.theme_doc)
        self._init_styles()

        # Formats
        self.format_repo = FormatRepository()
        self.formats_doc = self.format_repo.document
        self.formats = self.format_repo.formats

        # Layout
        container = ttk.Frame(root, padding=12, style="Panel.TFrame")
        container.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.columnconfigure(2, weight=1)
        container.rowconfigure(3, weight=1)

        self.header = ttk.Label(container, text="BinarySlicer · JCI Edition", style="Header.TLabel")
        self.header.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))

        toolbar = ttk.Frame(container, padding=(12, 10), style="Panel.TFrame")
        toolbar.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E))
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Input", style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.input_entry = ttk.Entry(toolbar, width=64, style="Input.TEntry")
        self.input_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))

        self.btn_calc = ttk.Button(toolbar, text="Calculate", bootstyle="primary", command=self.on_calculate)
        self.btn_calc.grid(row=0, column=2, padx=8)

        action_frame = ttk.Frame(toolbar, style="Panel.TFrame")
        action_frame.grid(row=0, column=3, padx=4, sticky=tk.E)
        ttk.Button(action_frame, text="Copy", bootstyle="secondary", command=self.copy_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Export CSV", bootstyle="secondary", command=self.export_csv).pack(side=tk.LEFT, padx=2)
        self.btn_theme = ttk.Button(
            action_frame, text="Toggle Theme", bootstyle="secondary", command=self.toggle_theme
        )
        self.btn_theme.pack(side=tk.LEFT, padx=(6, 0))

        options = ttk.Frame(container, padding=(12, 6), style="Panel.TFrame")
        options.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 4))
        options.columnconfigure(6, weight=1)

        ttk.Label(options, text="Options", style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W)
        self.show_fails = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options,
            text="Show parity failures (diagnostic)",
            variable=self.show_fails,
            style="TCheckbutton",
            command=self._refresh_diagnostics_tree,
        ).grid(row=0, column=1, padx=(12, 8), sticky=tk.W)
        self.reverse_bits = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options,
            text="Reverse bit order",
            variable=self.reverse_bits,
            style="TCheckbutton",
            command=self._on_reverse_toggle,
        ).grid(row=0, column=2, padx=(0, 12), sticky=tk.W)

        ttk.Label(options, text="Compatible slicing:", style="Muted.TLabel").grid(row=0, column=3, padx=(8, 4))
        self.slice_mode = tk.StringVar(value="auto")
        ttk.Radiobutton(options, text="Auto", value="auto", variable=self.slice_mode).grid(row=0, column=4, padx=2)
        ttk.Radiobutton(options, text="Leftmost", value="left", variable=self.slice_mode).grid(row=0, column=5, padx=2)
        ttk.Radiobutton(options, text="Rightmost", value="right", variable=self.slice_mode).grid(row=0, column=6, padx=2)

        main = ttk.Frame(container, padding=(0, 8), style="Panel.TFrame")
        main.grid(row=3, column=0, columnspan=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        self.summary_frame = ttk.Frame(main, padding=12, style="Panel.TFrame")
        self.summary_frame.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(0, 6))
        self.summary_frame.rowconfigure(1, weight=1)
        ttk.Label(self.summary_frame, text="Summary", style="Header.TLabel").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        summary_body = ttk.Frame(self.summary_frame, style="Panel.TFrame")
        summary_body.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        summary_body.rowconfigure(0, weight=1)
        summary_body.columnconfigure(0, weight=1)
        self.summary_text = tk.Text(summary_body, wrap=tk.WORD, height=24, relief=tk.FLAT, borderwidth=6)
        self.summary_text.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        summary_scroll = ttk.Scrollbar(summary_body, orient=tk.VERTICAL, command=self.summary_text.yview)
        summary_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.summary_text.configure(yscrollcommand=summary_scroll.set)

        notebook_container = ttk.Frame(main, padding=12, style="Panel.TFrame")
        notebook_container.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(6, 0))
        notebook_container.rowconfigure(0, weight=1)
        notebook_container.columnconfigure(0, weight=1)

        self.nb = ttk.Notebook(notebook_container)
        self.nb.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        self.tab_table = ttk.Frame(self.nb, padding=8, style="Panel.TFrame")
        self.tab_diagnostics = ttk.Frame(self.nb, padding=8, style="Panel.TFrame")
        self.nb.add(self.tab_table, text="Table")
        self.nb.add(self.tab_diagnostics, text="Diagnostics")

        # Table view
        cols = ("Field", "Range", "Value", "Hex")
        self.tree = ttk.Treeview(self.tab_table, columns=cols, show="headings", style="Results.Treeview")
        for col in cols:
            anchor = tk.W
            width = 130 if col != "Field" else 200
            self.tree.heading(col, text=col)
            self.tree.column(col, stretch=True, anchor=anchor, width=width)
        self.tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.tab_table.rowconfigure(0, weight=1)
        self.tab_table.columnconfigure(0, weight=1)
        self.copy_table_btn = ttk.Button(
            self.tab_table, text="Copy Selected", bootstyle="secondary", command=self.copy_selected_table
        )
        self.copy_table_btn.grid(row=1, column=0, sticky=tk.W, pady=6)

        # Diagnostics tab
        diag_body = ttk.Frame(self.tab_diagnostics, style="Panel.TFrame")
        diag_body.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        diag_body.columnconfigure(0, weight=1)
        diag_body.rowconfigure(0, weight=1)
        diag_body.rowconfigure(1, weight=2)

        diag_columns = ("Type", "Coverage", "Status", "Expected", "Actual", "DataLen", "ParityBit", "Gate")
        self.diagnostics_tree = ttk.Treeview(
            diag_body,
            columns=diag_columns,
            show="headings",
            style="Results.Treeview",
            height=8,
        )
        for col in diag_columns:
            anchor = tk.W
            width = 110 if col not in {"Type", "Coverage"} else 140
            self.diagnostics_tree.heading(col, text=col)
            self.diagnostics_tree.column(col, stretch=True, anchor=anchor, width=width)
        diag_scroll = ttk.Scrollbar(diag_body, orient=tk.VERTICAL, command=self.diagnostics_tree.yview)
        diag_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.diagnostics_tree.configure(yscrollcommand=diag_scroll.set)
        self.diagnostics_tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(0, 6))

        diag_text_frame = ttk.Frame(diag_body, style="Panel.TFrame")
        diag_text_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        diag_text_frame.columnconfigure(0, weight=1)
        diag_text_frame.rowconfigure(0, weight=1)
        self.diagnostics_text = tk.Text(diag_text_frame, wrap=tk.WORD, height=12, relief=tk.FLAT, borderwidth=6)
        self.diagnostics_text.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        diag_text_scroll = ttk.Scrollbar(diag_text_frame, orient=tk.VERTICAL, command=self.diagnostics_text.yview)
        diag_text_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.diagnostics_text.configure(yscrollcommand=diag_text_scroll.set)
        diag_actions = ttk.Frame(diag_text_frame, style="Panel.TFrame")
        diag_actions.grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Button(diag_actions, text="Copy diagnostics", bootstyle="secondary", command=self.copy_diagnostics).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.tab_diagnostics.rowconfigure(0, weight=1)
        self.tab_diagnostics.columnconfigure(0, weight=1)

        # Status
        cfg_dir = user_config_dir()
        self.status = ttk.Label(
            container,
            text=f"Formats loaded: {len(self.formats)} | Config: {cfg_dir}",
            style="Muted.TLabel",
        )
        self.status.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        if self.format_repo.last_errors:
            self.status.configure(text=f"Loaded with warnings: {self.format_repo.last_errors[0]}")

        # Menu
        self._build_menu()

        # Keyboard shortcuts
        shortcuts = {
            "<Control-i>": self._import_formats,
            "<Control-e>": self._export_formats,
            "<Control-t>": self.toggle_theme,
            "<Control-q>": self.root.destroy,
            "<Command-i>": self._import_formats,
            "<Command-e>": self._export_formats,
            "<Command-t>": self.toggle_theme,
            "<Command-q>": self.root.destroy,
        }
        for key, handler in shortcuts.items():
            self.root.bind(key, lambda event, h=handler: h())

        self.last_rows_for_csv: list[dict] = []
        self.last_binary_used = ""
        self.last_working_bits = ""
        self.last_input_meta: dict = {}
        self.last_format_checks: list[dict] = []

        self._apply_theme()
        self._refresh_diagnostics_tree()

    # ---------------- Theme helpers ----------------
    def _init_styles(self) -> None:
        self.style = getattr(self.root, "style", tb.Style(master=self.root))

    def _apply_theme(self) -> None:
        theme = self.theme
        apply_bootstrap_theme(self.style, self.theme_mode, theme)
        try:
            self.style.theme_use(self.theme_mode)
        except tk.TclError:
            # Safety fallback so the UI still renders even if a theme is missing.
            self.style.theme_use("clam")

        panel = theme.get("panel", theme.get("bg"))
        panel2 = theme.get("panel2", panel)
        accent = theme.get("accent", "#0399CC")
        accent2 = theme.get("accent2", accent)
        border = theme.get("border", "#d9dce5")
        text = theme.get("text", "#1d2230")
        muted = theme.get("muted", text)
        select = theme.get("select", accent)
        info = theme.get("info", accent2)
        on_accent = self._contrast_color(accent)
        on_select = self._contrast_color(select)
        base_font = ("Segoe UI", 10)
        mono_font = ("Consolas", 10)

        self.style.configure(".", background=theme.get("bg", "#f2f2f2"), foreground=text, font=base_font)
        self.root.configure(bg=theme.get("bg", "#f2f2f2"))
        self.style.configure("TLabel", font=base_font)
        self.style.configure("Muted.TLabel", font=base_font)
        self.style.configure("TCheckbutton", font=base_font)
        self.style.configure("TRadiobutton", font=base_font)
        self.style.configure("TNotebook.Tab", font=base_font)
        self.style.configure("Results.Treeview", font=base_font)
        self.style.configure("Results.Treeview.Heading", font=("Segoe UI Semibold", 10))
        self.style.map(
            "Results.Treeview",
            background=[("selected", select)],
            foreground=[("selected", on_select)],
            bordercolor=[("focus", info)],
        )

        # Style for the input entry (ttk.Entry uses styles, not insertbackground/selectbackground options)
        self.style.configure(
            "Input.TEntry",
            fieldbackground=panel2,
            foreground=text,
            padding=(8, 6),
        )

        # Apply the style to the existing entry widget
        self.input_entry.configure(style="Input.TEntry")


        self._apply_text_theme(self.summary_text, panel, text, border, mono_font, select, on_select)
        self._apply_text_theme(self.diagnostics_text, panel, text, border, mono_font, select, on_select)
        self._apply_treeview_tags()

    def _apply_text_theme(
        self,
        widget: tk.Text,
        bg: str,
        fg: str,
        border: str,
        font: tuple[str, int],
        select_bg: str,
        select_fg: str,
    ) -> None:
        widget.configure(
            bg=bg,
            fg=fg,
            insertbackground=fg,
            highlightbackground=border,
            highlightcolor=border,
            selectbackground=select_bg,
            selectforeground=select_fg,
            font=font,
        )

    def _apply_treeview_tags(self) -> None:
        panel = self.theme.get("panel", "#ffffff")
        alt = self._mix(panel, self.theme.get("bg", "#f5f6fb"), 0.08)
        self.tree.tag_configure("even", background=panel)
        self.tree.tag_configure("odd", background=alt)
        self.tree.tag_configure("value_mono", font=("Consolas", 10))

        if hasattr(self, "diagnostics_tree"):
            self.diagnostics_tree.tag_configure("even", background=panel)
            self.diagnostics_tree.tag_configure("odd", background=alt)
            self.diagnostics_tree.tag_configure("status_ok", foreground=self.theme.get("ok", "#29B582"))
            self.diagnostics_tree.tag_configure("status_fail", foreground=self.theme.get("error", "#E2555D"))
            self.diagnostics_tree.tag_configure("status_warn", foreground=self.theme.get("warn", "#7DBA00"))
            self.diagnostics_tree.tag_configure("status_neutral", foreground=self.theme.get("muted", "#9aa0ad"))

    @staticmethod
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

    def _contrast_color(self, color: str) -> str:
        color = color.lstrip("#")
        r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        return "#000000" if luma > 186 else "#ffffff"

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state=tk.DISABLED)

    def _clear_text(self, widget: tk.Text) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)

    def _working_bits(self, binary_string: str) -> str:
        return binary_string[::-1] if self.reverse_bits.get() else binary_string

    def _on_reverse_toggle(self) -> None:
        if self.last_binary_used:
            self._render_for_binary(self.last_binary_used, self.last_input_meta)
        else:
            self._refresh_diagnostics_tree()
        state = "ON" if self.reverse_bits.get() else "OFF"
        self.status.configure(text=f"Reverse bit order {state}")

    def toggle_theme(self) -> None:
        modes = list(available_themes())
        next_idx = (modes.index(self.theme_mode) + 1) % len(modes)
        self.theme_mode = modes[next_idx]
        self.theme = resolve_theme(self.theme_mode, self.theme_doc)
        self._apply_theme()
        self.theme_doc["last_mode"] = self.theme_mode
        save_theme_document(self.theme_doc)
        self.status.configure(text=f"Theme set to {self.theme_mode} mode")

    # ---------------- Menu ----------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Import Formats", command=self._import_formats)
        file_menu.add_command(label="Export Formats", command=self._export_formats)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Manage Formats", command=self._open_manage_formats)
        edit_menu.add_command(label="Self Test", command=self._self_test_dialog)
        menubar.add_cascade(label="Tools", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Toggle Theme", command=self.toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    # ---------------- Menu callbacks ----------------
    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "BinarySlicer\nParse binary/hex payloads into known access control formats.",
        )

    def _import_formats(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Import formats",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                incoming = json.load(handle)
        except json.JSONDecodeError:
            messagebox.showerror("Import", "Selected file is not valid JSON.")
            return
        self.format_repo.merge(incoming)
        self.formats_doc = self.format_repo.document
        self.formats = self.format_repo.formats
        if self.format_repo.last_errors:
            self.status.configure(text=f"Import warnings: {self.format_repo.last_errors[0]}")
        else:
            self.status.configure(text=f"Formats loaded: {len(self.formats)} (merged)")

    def _export_formats(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Export formats",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.formats_doc, handle, indent=2)
        self.status.configure(text=f"Formats exported to {path}")

    # ---------------- Manage formats ----------------
    def _open_manage_formats(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Manage Formats")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(frame, columns=("Name", "Bits"), show="headings", height=12)
        tree.heading("Name", text="Name")
        tree.heading("Bits", text="Bit Length")
        tree.column("Name", width=240, anchor=tk.W)
        tree.column("Bits", width=80, anchor=tk.W)
        tree.grid(row=0, column=0, columnspan=4, sticky=(tk.N, tk.S, tk.E, tk.W))

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=4, sticky=(tk.N, tk.S))
        tree.configure(yscrollcommand=scrollbar.set)

        for fmt in self.formats_doc.get("formats", []):
            tree.insert("", tk.END, values=(fmt.get("name"), fmt.get("bit_length")))

        btn_add = ttk.Button(frame, text="Add", bootstyle="secondary", command=lambda: self._edit_format(win, None, tree))
        btn_add.grid(row=1, column=0, sticky=tk.W, pady=6)

        btn_edit = ttk.Button(
            frame,
            text="Edit",
            bootstyle="secondary",
            command=lambda: self._edit_format(win, self._selected_format(tree), tree),
        )
        btn_edit.grid(row=1, column=1, sticky=tk.W, pady=6)

        btn_clone = ttk.Button(frame, text="Clone", bootstyle="secondary", command=lambda: self._clone_selected_format(tree))
        btn_clone.grid(row=1, column=2, sticky=tk.W, pady=6)

        btn_delete = ttk.Button(frame, text="Delete", bootstyle="secondary", command=lambda: self._delete_selected_format(tree))
        btn_delete.grid(row=1, column=3, sticky=tk.W, pady=6)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(0, weight=1)

        win.wait_window()

    def _selected_format(self, tree: ttk.Treeview) -> dict | None:
        item = tree.focus()
        if not item:
            return None
        name = tree.item(item, "values")[0]
        return next((f for f in self.formats_doc.get("formats", []) if f.get("name") == name), None)

    def _delete_selected_format(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if not item:
            return
        name = tree.item(item, "values")[0]
        if messagebox.askyesno("Delete", f"Delete format '{name}'?"):
            self.formats_doc["formats"] = [f for f in self.formats_doc.get("formats", []) if f.get("name") != name]
            self.format_repo.update(self.formats_doc)
            self.formats = self.format_repo.formats
            tree.delete(item)
            if self.format_repo.last_errors:
                self.status.configure(text=f"Delete completed with warnings: {self.format_repo.last_errors[0]}")
            else:
                self.status.configure(text=f"Formats loaded: {len(self.formats)} (deleted '{name}')")

    def _clone_selected_format(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if not item:
            return
        name = tree.item(item, "values")[0]
        source = next((f for f in self.formats_doc.get("formats", []) if f.get("name") == name), None)
        if not source:
            return
        clone = json.loads(json.dumps(source))
        clone["name"] = source.get("name", "Format") + " (Copy)"
        self.formats_doc.setdefault("formats", []).append(clone)
        self.format_repo.update(self.formats_doc)
        self.formats = self.format_repo.formats
        tree.insert("", tk.END, values=(clone.get("name"), clone.get("bit_length")))
        if self.format_repo.last_errors:
            self.status.configure(text=f"Clone completed with warnings: {self.format_repo.last_errors[0]}")
        else:
            self.status.configure(text=f"Formats loaded: {len(self.formats)} (cloned)")

    def _edit_format(self, parent: tk.Misc, fmt: dict | None, tree: ttk.Treeview) -> None:
        win = tk.Toplevel(parent)
        win.title("Edit Format" if fmt else "Add Format")
        win.transient(parent)
        win.grab_set()

        body = ttk.Frame(win, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Name").grid(row=0, column=0, sticky=tk.W)
        name_var = tk.StringVar(value=fmt.get("name") if fmt else "")
        ttk.Entry(body, textvariable=name_var, width=40).grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(body, text="Bit Length").grid(row=1, column=0, sticky=tk.W)
        bitlen_var = tk.StringVar(value=str(fmt.get("bit_length")) if fmt else "")
        ttk.Entry(body, textvariable=bitlen_var, width=12).grid(row=1, column=1, sticky=tk.W)

        fields_frame = ttk.Labelframe(body, text="Fields (ranges)")
        fields_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=6)
        field_columns = ("Name", "Start", "End", "Role", "View", "Hidden")
        fields_tree = ttk.Treeview(fields_frame, columns=field_columns, show="headings", height=6)
        for column in field_columns:
            fields_tree.heading(column, text=column)
            width = 140 if column == "Name" else 90
            fields_tree.column(column, anchor=tk.W, width=width)
        fields_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        fields_tree._payloads = {}  # type: ignore[attr-defined]
        ttk.Button(fields_frame, text="Add Field", bootstyle="secondary", command=lambda: self._add_field_row(fields_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(fields_frame, text="Edit Field", bootstyle="secondary", command=lambda: self._edit_field_row(fields_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(fields_frame, text="Delete Field", bootstyle="secondary", command=lambda: self._del_field_row(fields_tree)).grid(row=1, column=2, pady=4)

        parity_frame = ttk.Labelframe(body, text="Parity rules")
        parity_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        parity_tree = ttk.Treeview(parity_frame, columns=("Type", "Start", "End"), show="headings", height=5)
        for column in ("Type", "Start", "End"):
            parity_tree.heading(column, text=column)
            parity_tree.column(column, anchor=tk.W, width=120)
        parity_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        ttk.Button(parity_frame, text="Add Rule", bootstyle="secondary", command=lambda: self._add_parity_row(parity_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(parity_frame, text="Edit Rule", bootstyle="secondary", command=lambda: self._edit_parity_row(parity_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(parity_frame, text="Delete Rule", bootstyle="secondary", command=lambda: self._del_parity_row(parity_tree)).grid(row=1, column=2, pady=4)

        if fmt:
            for field in fmt.get("fields", []):
                name = field.get("name")
                start = field.get("start")
                end = field.get("end")
                role = field.get("role", field.get("type", "field")) or "field"
                view = field.get("view", field.get("decode", "")) or ""
                hidden = "yes" if field.get("hidden") else ""
                item_id = fields_tree.insert("", tk.END, values=(name, start, end, role, view, hidden))
                extras = {k: v for k, v in field.items() if k not in {"name", "start", "end", "role", "view", "decode", "hidden"}}
                fields_tree._payloads[item_id] = extras  # type: ignore[attr-defined]
            for rule in fmt.get("parity", []):
                rule_type = rule.get("type", "even").lower()
                for rng in rule.get("ranges", []):
                    parity_tree.insert("", tk.END, values=(rule_type, rng.get("start"), rng.get("end")))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=8)
        ttk.Button(
            actions,
            text="Save",
            bootstyle="primary",
            command=lambda: self._save_format(
                win,
                fmt,
                name_var,
                bitlen_var,
                fields_tree,
                parity_tree,
                tree,
            ),
        ).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Cancel", bootstyle="secondary", command=win.destroy).pack(side=tk.RIGHT, padx=8)

        win.wait_window()

    def _add_field_row(self, tree: ttk.Treeview) -> None:
        self._field_edit_dialog(tree, None)

    def _edit_field_row(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if item:
            values = tree.item(item, "values")
            self._field_edit_dialog(tree, (item, values))

    def _del_field_row(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if item:
            payloads = getattr(tree, "_payloads", {})
            payloads.pop(item, None)
            tree.delete(item)

    def _field_edit_dialog(self, tree: ttk.Treeview, row) -> None:
        payloads = getattr(tree, "_payloads", {})
        win = tk.Toplevel(self.root)
        win.title("Field")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        current = row[1] if row else ["", "", "", "field", "", ""]
        ttk.Label(frame, text="Name").grid(row=0, column=0, sticky=tk.W)
        name_var = tk.StringVar(value=current[0] if current else "")
        ttk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="Start").grid(row=1, column=0, sticky=tk.W)
        start_var = tk.StringVar(value=current[1] if len(current) > 1 else "0")
        ttk.Entry(frame, textvariable=start_var, width=8).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(frame, text="End").grid(row=2, column=0, sticky=tk.W)
        end_var = tk.StringVar(value=current[2] if len(current) > 2 else "0")
        ttk.Entry(frame, textvariable=end_var, width=8).grid(row=2, column=1, sticky=tk.W)

        ttk.Label(frame, text="Role").grid(row=3, column=0, sticky=tk.W)
        role_var = tk.StringVar(value=current[3] if len(current) > 3 else "field")
        ttk.Combobox(frame, textvariable=role_var, values=["field", "parity"], state="readonly").grid(
            row=3, column=1, sticky=(tk.W, tk.E)
        )

        ttk.Label(frame, text="View").grid(row=4, column=0, sticky=tk.W)
        view_var = tk.StringVar(value=current[4] if len(current) > 4 else "")
        ttk.Entry(frame, textvariable=view_var).grid(row=4, column=1, sticky=(tk.W, tk.E))

        hidden_var = tk.BooleanVar(value=(str(current[5]).lower() in ("yes", "true", "1")))
        ttk.Checkbutton(frame, text="Hidden", variable=hidden_var).grid(row=5, column=0, sticky=tk.W, pady=4)

        def save_row() -> None:
            try:
                start = int(start_var.get())
                end = int(end_var.get())
                if end < start:
                    messagebox.showerror("Field", "End must be >= Start")
                    return
            except ValueError:
                messagebox.showerror("Field", "Start/End must be integers")
                return
            values = (
                name_var.get(),
                start,
                end,
                role_var.get() or "field",
                view_var.get(),
                "yes" if hidden_var.get() else "",
            )
            if row:
                tree.item(row[0], values=values)
                existing_extras = payloads.get(row[0], {})
                payloads[row[0]] = existing_extras
            else:
                item_id = tree.insert("", tk.END, values=values)
                payloads[item_id] = {}
            win.destroy()

        ttk.Button(frame, text="Save", bootstyle="primary", command=save_row).grid(row=6, column=0, columnspan=2, pady=8)
        ttk.Button(frame, text="Cancel", bootstyle="secondary", command=win.destroy).grid(row=7, column=0, columnspan=2, pady=4)

        win.wait_window()

    def _add_parity_row(self, tree: ttk.Treeview) -> None:
        self._parity_edit_dialog(tree, None)

    def _edit_parity_row(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if item:
            values = tree.item(item, "values")
            self._parity_edit_dialog(tree, (item, values))

    def _del_parity_row(self, tree: ttk.Treeview) -> None:
        item = tree.focus()
        if item:
            tree.delete(item)

    def _parity_edit_dialog(self, tree: ttk.Treeview, row) -> None:
        win = tk.Toplevel(self.root)
        win.title("Parity Rule")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Type").grid(row=0, column=0, sticky=tk.W)
        type_var = tk.StringVar(value=row[1][0] if row else "even")
        ttk.Combobox(frame, textvariable=type_var, values=["even", "odd"], state="readonly").grid(
            row=0, column=1, sticky=(tk.W, tk.E)
        )

        ttk.Label(frame, text="Start").grid(row=1, column=0, sticky=tk.W)
        start_var = tk.StringVar(value=row[1][1] if row else "0")
        ttk.Entry(frame, textvariable=start_var, width=8).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(frame, text="End").grid(row=2, column=0, sticky=tk.W)
        end_var = tk.StringVar(value=row[1][2] if row else "1")
        ttk.Entry(frame, textvariable=end_var, width=8).grid(row=2, column=1, sticky=tk.W)

        def save_rule() -> None:
            try:
                start = int(start_var.get())
                end = int(end_var.get())
                if end < start:
                    messagebox.showerror("Parity", "End must be >= Start")
                    return
            except ValueError:
                messagebox.showerror("Parity", "Start/End must be integers")
                return
            values = (type_var.get(), start, end)
            if row:
                tree.item(row[0], values=values)
            else:
                tree.insert("", tk.END, values=values)
            win.destroy()

        ttk.Button(frame, text="Save", bootstyle="primary", command=save_rule).grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(frame, text="Cancel", bootstyle="secondary", command=win.destroy).grid(row=4, column=0, columnspan=2, pady=4)

        win.wait_window()

    def _save_format(
        self,
        window: tk.Toplevel,
        original: dict | None,
        name_var: tk.StringVar,
        bitlen_var: tk.StringVar,
        fields_tree: ttk.Treeview,
        parity_tree: ttk.Treeview,
        listing: ttk.Treeview,
    ) -> None:
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Format", "Name is required")
            return
        try:
            bitlen = int(bitlen_var.get())
            if bitlen <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Format", "Bit length must be a positive integer")
            return

        fields = []
        payloads = getattr(fields_tree, "_payloads", {})
        for item in fields_tree.get_children(""):
            fname, start, end, role, view, hidden = fields_tree.item(item, "values")
            try:
                start_int = int(start)
                end_int = int(end)
            except (TypeError, ValueError):
                messagebox.showerror("Field", f"Field '{fname}' has invalid bounds.")
                return
            field_payload = dict(payloads.get(item, {}))
            field_payload.update({"name": fname, "start": start_int, "end": end_int})
            if role:
                field_payload["role"] = role
            if view:
                field_payload["view"] = view
            else:
                field_payload.pop("view", None)
            if hidden:
                field_payload["hidden"] = True
            else:
                field_payload.pop("hidden", None)
            fields.append(field_payload)

        parity = []
        for item in parity_tree.get_children(""):
            ptype, start, end = parity_tree.item(item, "values")
            parity.append({"type": ptype, "ranges": [{"start": int(start), "end": int(end)}]})

        entry = {"name": name, "bit_length": bitlen, "fields": fields, "parity": parity}

        try:
            normalized = normalize_format_entry(entry)
            validate_format_entry(entry, normalized)
        except FormatValidationError as exc:
            messagebox.showerror("Format", str(exc))
            return

        if original and original in self.formats_doc.get("formats", []):
            idx = self.formats_doc["formats"].index(original)
            self.formats_doc["formats"][idx] = entry
        else:
            self.formats_doc.setdefault("formats", []).append(entry)

        self.format_repo.update(self.formats_doc)
        self.formats = self.format_repo.formats

        listing.delete(*listing.get_children(""))
        for fmt in self.formats_doc.get("formats", []):
            listing.insert("", tk.END, values=(fmt.get("name"), fmt.get("bit_length")))

        if self.format_repo.last_errors:
            self.status.configure(text=f"Formats saved with warnings: {self.format_repo.last_errors[0]}")
        else:
            self.status.configure(text=f"Formats loaded: {len(self.formats)} (saved)")
        window.destroy()

    # ---------------- Self test ----------------
    def _self_test_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Self Test")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Binary Payload").grid(row=0, column=0, sticky=tk.W)
        payload_entry = ttk.Entry(frame, width=64)
        payload_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="Format Name").grid(row=1, column=0, sticky=tk.W)
        fmt_entry = ttk.Entry(frame, width=40)
        fmt_entry.grid(row=1, column=1, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="Expected Field (regex)").grid(row=2, column=0, sticky=tk.W)
        field_entry = ttk.Entry(frame, width=40)
        field_entry.grid(row=2, column=1, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="Expected Value (regex)").grid(row=3, column=0, sticky=tk.W)
        value_entry = ttk.Entry(frame, width=40)
        value_entry.grid(row=3, column=1, sticky=(tk.W, tk.E))

        output = tk.Text(frame, height=10, width=60, state=tk.DISABLED)
        output.grid(row=4, column=0, columnspan=2, pady=8)

        def run_test() -> None:
            binary = payload_entry.get().strip()
            fmt_name = fmt_entry.get().strip()
            field_pattern = field_entry.get().strip()
            value_pattern = value_entry.get().strip()

            if not BIT_RE.match(binary):
                messagebox.showerror("Self Test", "Binary payload must contain only 0/1 characters.")
                return
            fmt = self.formats.get(fmt_name)
            if not fmt:
                messagebox.showerror("Self Test", f"Unknown format '{fmt_name}'.")
                return
            fields = extract_fields(binary, fmt)
            if field_pattern:
                regex = re.compile(field_pattern)
                if not any(regex.search(name) for name in fields):
                    messagebox.showerror("Self Test", "Field pattern did not match any field names.")
                    return
            if value_pattern:
                regex = re.compile(value_pattern)
                if not any(regex.search(str(meta["int"])) for meta in fields.values()):
                    messagebox.showerror("Self Test", "Value pattern did not match any field values.")
                    return

            output.configure(state=tk.NORMAL)
            output.delete("1.0", tk.END)
            for field, meta in fields.items():
                output.insert(
                    tk.END,
                    f"{field}: {meta['int']} (hex {meta['hex']}), bits[{meta['len']}]={meta['bits']}\n",
                )
            output.configure(state=tk.DISABLED)

        ttk.Button(frame, text="Run", bootstyle="primary", command=run_test).grid(row=5, column=0, pady=6)
        ttk.Button(frame, text="Close", bootstyle="secondary", command=win.destroy).grid(row=5, column=1, pady=6)

        win.wait_window()

    # ---------------- Calculate / Render ----------------
    def on_calculate(self) -> None:
        input_data = self.input_entry.get()
        binary_string, error, input_meta = process_input(input_data)
        if error:
            messagebox.showerror("Error", error)
            return
        self._render_for_binary(binary_string, input_meta)

    def _render_for_binary(self, binary_string: str, input_meta: dict | None = None) -> None:
        self.last_binary_used = binary_string
        self.last_input_meta = input_meta or {}
        working_bits = self._working_bits(binary_string)
        self.last_working_bits = working_bits
        self._clear_text(self.summary_text)
        self._clear_text(self.diagnostics_text)

        reverse_note = " (reverse bit order ON)" if self.reverse_bits.get() else ""
        summary_lines: list[str] = []
        summary_lines.append(
            f"Working bits ({len(working_bits)} bits){reverse_note}:\n{format_binary_groups(working_bits)}\n\n"
        )
        if self.reverse_bits.get():
            summary_lines.append("Original input (unchanged):\n")
            summary_lines.append(f"{format_binary_groups(binary_string)}\n\n")

        exact, compatible = self._detect_formats(working_bits)
        diagnostics_context: dict = {
            "input": input_meta,
            "exact_matches": [name for name, _ in exact],
            "compatible_matches": [name for name, _ in compatible],
            "rendered": [],
            "auto_candidates": [],
            "slice_mode": self.slice_mode.get(),
            "reverse_bits": self.reverse_bits.get(),
        }

        if not exact and not compatible:
            summary_lines.append("No matching formats found.\n")
            self._set_text(self.summary_text, "".join(summary_lines))
            self._set_text(self.diagnostics_text, build_diagnostics_report(diagnostics_context))
            self._refresh_diagnostics_tree()
            return

        self.last_rows_for_csv = []
        self.tree.delete(*self.tree.get_children(""))
        self.last_format_checks = []

        rendered_any = False
        if exact:
            summary_lines.append("== Exact bit-length matches ==\n")
            rendered, diag, chunks = self._render_candidates(working_bits, exact, slice_mode=None)
            diagnostics_context["rendered"].extend(diag)
            summary_lines.extend(chunks)
            rendered_any |= rendered

        if compatible:
            summary_lines.append("== Compatible (input longer than known format) ==\n")
            summary_lines.append("These may indicate framing/padding.\n\n")
            rendered, diag, chunks = self._render_candidates(
                working_bits,
                compatible,
                slice_mode=self.slice_mode.get(),
            )
            diagnostics_context["rendered"].extend(diag)
            summary_lines.extend(chunks)
            rendered_any |= rendered

        if not rendered_any:
            summary_lines.append(
                "No formats passed parity in strict mode.\n"
                "Tip: Enable 'Show parity failures (diagnostic)' to inspect candidates.\n"
            )

        self._set_text(self.summary_text, "".join(summary_lines))
        self._set_text(self.diagnostics_text, build_diagnostics_report(diagnostics_context))
        self._refresh_diagnostics_tree()

    def _detect_formats(self, binary_string: str):
        exact = []
        compatible = []
        for name, fmt in self.formats.items():
            L = fmt.bit_length
            if len(binary_string) == L:
                exact.append((name, fmt))
            elif len(binary_string) > L:
                compatible.append((name, fmt))
        return exact, compatible

    def _render_candidates(
        self, binary_string: str, candidates: list[tuple], slice_mode: str | None
    ) -> tuple[bool, list[dict], list[str]]:
        if slice_mode == "auto":
            return self._render_auto_candidates(binary_string, candidates)
        rendered = False
        diagnostics: list[dict] = []
        summaries: list[str] = []
        for name, fmt in candidates:
            bit_length = fmt.bit_length
            if slice_mode is None:
                use_bits = binary_string
                display_name = name
            else:
                use_bits = binary_string[:bit_length] if slice_mode == "left" else binary_string[-bit_length:]
                display_name = name + (" (leftmost)" if slice_mode == "left" else " (rightmost)")
            parity_all_ok = self._parity_all_ok(use_bits, fmt)
            if slice_mode is not None and (not self.show_fails.get()) and not parity_all_ok:
                continue
            summary_block, diag_entry = self._render_format(use_bits, display_name, fmt, {"mode": slice_mode})
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            rendered = True
        return rendered, diagnostics, summaries

    def _render_auto_candidates(self, binary_string: str, candidates: list[tuple]) -> tuple[bool, list[dict], list[str]]:
        rendered = False
        diagnostics: list[dict] = []
        summaries: list[str] = []
        all_results: list[dict] = []
        for name, fmt in candidates:
            best = find_best_offsets(binary_string, fmt, step=1, top_n=3)
            for cand in best:
                all_results.append({"name": name, "fmt": fmt, "candidate": cand})
        if not all_results:
            return False, diagnostics, summaries
        all_results.sort(key=lambda c: c["candidate"]["score_key"], reverse=True)
        limit = max(3, min(len(all_results), 10))
        for entry in all_results[:limit]:
            cand = entry["candidate"]
            stats = cand["stats"]
            parity = cand["parity"]
            if not self.show_fails.get() and stats["gated_fail"] > 0:
                continue
            display_name = (
                f"{entry['name']} (auto offset +{cand['offset']}, "
                f"pass {stats['total_pass']}/{len(parity)}, gated_fail={stats['gated_fail']})"
            )
            summary_block, diag_entry = self._render_format(
                cand["bits"],
                display_name,
                entry["fmt"],
                {"mode": "auto", "offset": cand["offset"], "top_candidates": all_results[:limit]},
            )
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            rendered = True
        return rendered, diagnostics, summaries

    def _render_format(
        self, binary_string: str, name: str, fmt: NormalizedFormat, meta: dict | None = None
    ) -> tuple[str, dict]:
        meta = meta or {}
        summary_lines: list[str] = [f"Format: {name}\n"]
        fields = extract_fields(binary_string, fmt)
        for field, meta in fields.items():
            if meta.get("hidden"):
                continue
            summary_lines.append(
                f"  {field:14}: {meta['int']} (hex {meta['hex']}), bits[{meta['len']}]={meta['bits']}\n"
            )
            start, end = meta["range"]
            idx = len(self.tree.get_children(""))
            tags = ("even",) if idx % 2 == 0 else ("odd",)
            tags += ("value_mono",)
            self.tree.insert("", tk.END, values=(field, f"{start}–{end}", meta["int"], meta["hex"]), tags=tags)
            self.last_rows_for_csv.append(
                {
                    "Format": name,
                    "Field": field,
                    "Value": meta["int"],
                    "Hex": meta["hex"],
                    "BitLength": meta["len"],
                    "Bits": meta["bits"],
                }
            )
        parity = verify_parity(binary_string, fmt)
        if parity:
            for result in parity:
                if result["ok"]:
                    status = "OK"
                elif result["ok"] is False:
                    status = "FAIL"
                else:
                    status = "(no parity bit)"
                note = " (advisory)" if not result.get("gate", True) else ""
                parity_loc = f"; parity_bit={result.get('parity_bit')}" if result.get("parity_bit") is not None else ""
                summary_lines.append(
                    f"  Parity {result['type']:4} {result['coverage'][0]}–{result['coverage'][1]}: {status}{note} "
                    f"(expected {result['expected']}, actual {result['actual']}; data_len={result['data_len']}{parity_loc})\n"
                )
            self.last_format_checks = parity
        summary_lines.append("\n")
        return "\n".join(summary_lines), {
            "name": name,
            "bit_length": len(binary_string),
            "parity": parity,
            "parity_stats": parity_score(parity) if parity else None,
            "meta": meta,
        }

    def _parity_all_ok(self, binary_string: str, fmt: NormalizedFormat) -> bool:
        parity = verify_parity(binary_string, fmt)
        if not parity:
            return True
        for result in parity:
            if result.get("gate", True) and result.get("ok") is False:
                return False
        return True

    def _diagnostic_status(self, result: dict) -> tuple[str, str]:
        ok = result.get("ok")
        gate = result.get("gate", True)
        if ok is True:
            return "OK", "status_ok"
        if ok is False:
            return ("FAIL" if gate else "Advisory"), ("status_fail" if gate else "status_warn")
        return "Not evaluated", "status_neutral"

    def _refresh_diagnostics_tree(self) -> None:
        if not hasattr(self, "diagnostics_tree"):
            return
        self.diagnostics_tree.delete(*self.diagnostics_tree.get_children(""))

        show_all = self.show_fails.get()
        rows = self.last_format_checks or []
        if not rows:
            self.diagnostics_tree.insert(
                "",
                tk.END,
                values=("No parity checks", "", "Not evaluated", "", "", "", "", ""),
                tags=("status_neutral",),
            )
            return

        visible_idx = 0
        for result in rows:
            if not show_all and result.get("ok") is not False:
                continue
            coverage = result.get("coverage") or ("?", "?")
            coverage_text = f"{coverage[0]}–{coverage[1]}"
            status_text, status_tag = self._diagnostic_status(result)
            parity_bit = result.get("parity_bit")
            values = (
                result.get("label") or result.get("type", ""),
                coverage_text,
                status_text,
                result.get("expected", ""),
                result.get("actual", ""),
                result.get("data_len", ""),
                "-" if parity_bit is None else parity_bit,
                "Yes" if result.get("gate", True) else "Advisory",
            )
            row_tags = ("even",) if visible_idx % 2 == 0 else ("odd",)
            row_tags += (status_tag,)
            self.diagnostics_tree.insert("", tk.END, values=values, tags=row_tags)
            visible_idx += 1

        if visible_idx == 0:
            self.diagnostics_tree.insert(
                "",
                tk.END,
                values=("No parity failures to show", "", "OK", "", "", "", "", ""),
                tags=("status_neutral",),
            )

    # ---------------- Copy / Export ----------------
    def copy_results(self) -> None:
        prev_state = self.summary_text.cget("state")
        self.summary_text.configure(state=tk.NORMAL)
        text = self.summary_text.get("1.0", tk.END)
        if prev_state != tk.NORMAL:
            self.summary_text.configure(state=prev_state)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.configure(text="Results copied to clipboard.")

    def copy_diagnostics(self) -> None:
        prev_state = self.diagnostics_text.cget("state")
        self.diagnostics_text.configure(state=tk.NORMAL)
        text = self.diagnostics_text.get("1.0", tk.END)
        if prev_state != tk.NORMAL:
            self.diagnostics_text.configure(state=prev_state)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.configure(text="Diagnostics copied to clipboard.")

    def copy_selected_table(self) -> None:
        selected = self.tree.focus()
        if not selected:
            return
        values = self.tree.item(selected, "values")
        copy_text = "\t".join(str(value) for value in values)
        self.root.clipboard_clear()
        self.root.clipboard_append(copy_text)
        self.status.configure(text="Selected row copied.")

    def export_csv(self) -> None:
        if not self.last_rows_for_csv:
            messagebox.showwarning("No data", "Please calculate first.")
            return
        default_name = f"CardExport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["Format", "Field", "Value", "Hex", "BitLength", "Bits"],
            )
            writer.writeheader()
            writer.writerows(self.last_rows_for_csv)
        self.status.configure(text=f"CSV exported to {path}")


def main() -> None:
    ensure_user_config_dir()
    log_dir = Path(user_config_dir()) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "logs.txt"

    try:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"BinarySlicer started at {datetime.now().isoformat()}\n")
    except OSError:
        pass

    try:
        root = tb.Window(themename="light_jci")
        base_dir = getattr(sys, "_MEIPASS", application_dir())
        ico_path = Path(base_dir) / "icons" / "jci_globe.ico"
        png_path = Path(base_dir) / "icons" / "jci_globe_256.png"
        try:
            if ico_path.exists():
                root.iconbitmap(ico_path)
            elif png_path.exists():
                icon = tk.PhotoImage(file=str(png_path))
                root.iconphoto(True, icon)
        except Exception:
            pass

        root.app = App(root)
        root.minsize(900, 560)
        root.mainloop()
    except Exception as exc:  # pragma: no cover - safety fallback
        import traceback

        traceback.print_exc()
        messagebox.showerror("Fatal error", f"An unexpected error occurred: {exc}")


if __name__ == "__main__":
    main()
