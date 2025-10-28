"""Tkinter UI for BinarySlicer."""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .decoder import clean_input, format_binary_groups, is_binary, is_hex, process_input
from .formats import (
    FormatRepository,
    NormalizedFormat,
    extract_fields,
    verify_parity,
)
from .paths import application_dir, ensure_user_config_dir, user_config_dir
from .theme import load_theme_document, save_theme_document

BIT_RE = re.compile(r"^[01]+$")


class App:
    """Main BinarySlicer application."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("BinarySlicer – JCI Edition")

        ensure_user_config_dir()

        # Theme
        self.theme_doc = load_theme_document()
        self.theme_mode = self.theme_doc.get("last_mode", "light")
        self.theme = self.theme_doc.get(self.theme_mode, self.theme_doc.get("light", {}))
        self._init_styles()
        self._apply_theme()

        # Formats
        self.format_repo = FormatRepository()
        self.formats_doc = self.format_repo.document
        self.formats = self.format_repo.formats

        # Derived format metadata
        self.format_bit_lengths: list[int] = []
        self.format_length_lookup: dict[int, list[str]] = {}
        self._refresh_format_lengths()

        # Hero header
        self.hero = tk.Frame(root, borderwidth=0)
        self.hero.grid(row=0, column=0, sticky=(tk.E, tk.W))
        self.hero.columnconfigure(0, weight=1)

        self.hero_content = tk.Frame(self.hero, borderwidth=0)
        self.hero_content.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=20, pady=(16, 12))
        self.hero_content.columnconfigure(0, weight=1)

        self.hero_badge = tk.Label(
            self.hero_content,
            text="JCI Tools",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=4,
        )
        self.hero_badge.grid(row=0, column=0, sticky=tk.W)

        self.hero_title = tk.Label(
            self.hero_content,
            text="BinarySlicer",
            font=("Segoe UI", 20, "bold"),
            pady=2,
        )
        self.hero_title.grid(row=1, column=0, sticky=tk.W)

        self.hero_subtitle = tk.Label(
            self.hero_content,
            text="Decode access control payloads with brand-aligned clarity.",
            font=("Segoe UI", 11),
            pady=2,
        )
        self.hero_subtitle.grid(row=2, column=0, sticky=tk.W)

        self.hero_accent = tk.Frame(self.hero, height=3, borderwidth=0)
        self.hero_accent.grid(row=1, column=0, sticky=(tk.E, tk.W))

        # Main container
        container = ttk.Frame(root, padding=(18, 16), style="AppContainer.TFrame")
        container.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # Input card
        input_card = ttk.Frame(container, padding=(16, 14), style="Card.TFrame")
        input_card.grid(row=0, column=0, columnspan=10, sticky=(tk.E, tk.W))
        input_card.columnconfigure(0, weight=1)

        ttk.Label(input_card, text="Payload Analyzer", style="SectionHeading.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(
            input_card,
            text="Paste binary or hexadecimal payloads; BinarySlicer automatically normalizes spacing, prefixes, and case.",
            style="Subtle.TLabel",
            wraplength=620,
        ).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(2, 10))

        entry_row = ttk.Frame(input_card, style="CardInner.TFrame")
        entry_row.grid(row=2, column=0, columnspan=4, sticky=(tk.E, tk.W))
        entry_row.columnconfigure(1, weight=1)

        ttk.Label(entry_row, text="Payload", style="FieldLabel.TLabel").grid(row=0, column=0, sticky=tk.W)
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(entry_row, textvariable=self.input_var, width=68)
        self.input_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(12, 12))

        quick_frame = ttk.Frame(entry_row, style="CardInner.TFrame")
        quick_frame.grid(row=0, column=2, sticky=tk.W)

        self.btn_paste = ttk.Button(
            quick_frame,
            text="Paste",
            style="Ghost.TButton",
            command=self.paste_from_clipboard,
            width=10,
        )
        self.btn_paste.grid(row=0, column=0, padx=(0, 6))

        self.btn_clear = ttk.Button(
            quick_frame,
            text="Clear",
            style="Ghost.TButton",
            command=self.clear_input,
            width=10,
        )
        self.btn_clear.grid(row=0, column=1)

        feedback_row = ttk.Frame(input_card, style="CardInner.TFrame")
        feedback_row.grid(row=3, column=0, columnspan=4, sticky=(tk.E, tk.W), pady=(12, 4))
        feedback_row.columnconfigure(0, weight=1)

        self.input_feedback = ttk.Label(
            feedback_row,
            text="Waiting for input…",
            style="Info.TLabel",
            wraplength=620,
        )
        self.input_feedback.grid(row=0, column=0, sticky=tk.W)

        progress_row = ttk.Frame(input_card, style="CardInner.TFrame")
        progress_row.grid(row=4, column=0, columnspan=4, sticky=(tk.E, tk.W), pady=(4, 12))
        progress_row.columnconfigure(0, weight=1)

        self.bit_progress = ttk.Progressbar(
            progress_row,
            orient=tk.HORIZONTAL,
            length=200,
            mode="determinate",
            maximum=100,
            style="Hero.Horizontal.TProgressbar",
        )
        self.bit_progress.grid(row=0, column=0, sticky=(tk.E, tk.W))

        self.bit_progress_label = ttk.Label(progress_row, text="", style="Subtle.TLabel")
        self.bit_progress_label.grid(row=1, column=0, sticky=tk.W, pady=(4, 0))

        action_row = ttk.Frame(input_card, style="CardInner.TFrame")
        action_row.grid(row=5, column=0, columnspan=4, sticky=(tk.E, tk.W))
        action_row.columnconfigure(0, weight=1)

        self.btn_calc = ttk.Button(
            action_row,
            text="Analyze Payload",
            style="Primary.TButton",
            command=self.on_calculate,
        )
        self.btn_calc.grid(row=0, column=0, sticky=tk.W)

        secondary_actions = ttk.Frame(action_row, style="CardInner.TFrame")
        secondary_actions.grid(row=0, column=1, sticky=tk.E)

        self.btn_copy = ttk.Button(
            secondary_actions,
            text="Copy Results",
            style="Accent.TButton",
            command=self.copy_results,
        )
        self.btn_copy.grid(row=0, column=0, padx=(0, 8))

        self.btn_export = ttk.Button(
            secondary_actions,
            text="Export CSV",
            style="Ghost.TButton",
            command=self.export_csv,
        )
        self.btn_export.grid(row=0, column=1)

        # Options card
        options_card = ttk.Frame(container, padding=(16, 12), style="Card.TFrame")
        options_card.grid(row=1, column=0, columnspan=10, sticky=(tk.E, tk.W), pady=(16, 0))
        for col in range(4):
            options_card.columnconfigure(col, weight=1)

        self.show_fails = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_card,
            text="Show parity failures (diagnostic)",
            variable=self.show_fails,
            style="Toggle.TCheckbutton",
        ).grid(row=0, column=0, sticky=tk.W)

        slice_frame = ttk.Frame(options_card, style="CardInner.TFrame")
        slice_frame.grid(row=0, column=1, sticky=tk.W)
        ttk.Label(slice_frame, text="Compatible slicing", style="FieldLabel.TLabel").grid(
            row=0, column=0, padx=(0, 12)
        )
        self.slice_mode = tk.StringVar(value="left")
        ttk.Radiobutton(
            slice_frame,
            text="Leftmost",
            value="left",
            variable=self.slice_mode,
            style="Segment.TRadiobutton",
        ).grid(row=0, column=1, padx=4)
        ttk.Radiobutton(
            slice_frame,
            text="Rightmost",
            value="right",
            variable=self.slice_mode,
            style="Segment.TRadiobutton",
        ).grid(row=0, column=2, padx=4)

        quick_tools = ttk.Frame(options_card, style="CardInner.TFrame")
        quick_tools.grid(row=0, column=2, sticky=tk.E)
        ttk.Button(
            quick_tools,
            text="Manage Formats…",
            style="Ghost.TButton",
            command=self._open_manage_formats,
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            quick_tools,
            text="Self Test",
            style="Ghost.TButton",
            command=self._self_test_dialog,
        ).grid(row=0, column=1)

        self.btn_theme = ttk.Button(
            options_card,
            text="Toggle Theme",
            style="Ghost.TButton",
            command=self.toggle_theme,
        )
        self.btn_theme.grid(row=0, column=3, sticky=tk.E)

        container.rowconfigure(2, weight=1)

        # Notebook
        self.nb = ttk.Notebook(container)
        self.nb.grid(row=2, column=0, columnspan=10, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(18, 0))
        container.columnconfigure(0, weight=1)

        self.tab_summary = ttk.Frame(self.nb)
        self.tab_table = ttk.Frame(self.nb)
        self.tab_visual = ttk.Frame(self.nb)
        self.nb.add(self.tab_summary, text="Summary")
        self.nb.add(self.tab_table, text="Table")
        self.nb.add(self.tab_visual, text="Parity Visualizer")

        # Summary text
        self.txt = tk.Text(self.tab_summary, width=100, height=26)
        self.txt.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.tab_summary.rowconfigure(0, weight=1)
        self.tab_summary.columnconfigure(0, weight=1)

        # Table view
        cols = ("Field", "Bits", "Int", "Hex")
        self.tree = ttk.Treeview(self.tab_table, columns=cols, show="headings")
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, stretch=True, anchor=tk.W, width=120)
        self.tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.tab_table.rowconfigure(0, weight=1)
        self.tab_table.columnconfigure(0, weight=1)
        self.copy_table_btn = ttk.Button(
            self.tab_table, text="Copy Selected", command=self.copy_selected_table
        )
        self.copy_table_btn.grid(row=1, column=0, sticky=tk.W, pady=6)

        # Visualizer canvas
        self.canvas = tk.Canvas(self.tab_visual, height=60)
        self.canvas.grid(row=0, column=0, sticky=(tk.E, tk.W), padx=4, pady=8)
        self.tab_visual.columnconfigure(0, weight=1)

        # Status
        cfg_dir = user_config_dir()
        self.status = ttk.Label(
            container,
            text=f"Ready • Formats: {len(self.formats)} • Config: {cfg_dir}",
            style="StatusBar.TLabel",
            anchor=tk.W,
        )
        self.status.grid(row=3, column=0, columnspan=10, sticky=(tk.W, tk.E), pady=(18, 0))

        # Menu
        self._build_menu()

        self.last_rows_for_csv: list[dict] = []
        self.last_binary_used = ""
        self.last_format_checks: list[dict] = []

        self._apply_theme_classic_widgets()
        self._apply_hero_theme()

        self.input_var.trace_add("write", lambda *_: self._update_input_feedback())
        self.input_entry.bind("<Return>", lambda _event: self.on_calculate())
        self.input_entry.bind("<Control-Return>", lambda _event: self.on_calculate())
        self.root.bind("<Control-l>", lambda _event: self.clear_input())
        self.root.bind("<Control-Shift-V>", lambda _event: self.paste_from_clipboard())

        self._update_input_feedback()

    # ---------------- Theme helpers ----------------
    def _init_styles(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

    def _apply_theme(self) -> None:
        theme = self.theme
        primary = theme.get("primary", "#1740b1")
        primary_dark = theme.get("primaryDark", primary)
        accent = theme.get("accent", "#ff7f32")
        bg = theme.get("bg", "#f2f2f2")
        panel = theme.get("panel", bg)
        text = theme.get("text", "#1f2933")
        muted = theme.get("mutedText", "#5a5f6b")
        border = theme.get("border", "#d7dce5")

        self.style.configure(".", font=("Segoe UI", 10))
        self.root.configure(bg=bg)
        self.style.configure("AppContainer.TFrame", background=bg)
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabelframe", background=bg)
        self.style.configure("TLabelframe.Label", background=bg, foreground=text)
        self.style.configure("TLabel", background=bg, foreground=text)
        self.style.configure("TCheckbutton", background=bg, foreground=text)
        self.style.configure("TRadiobutton", background=bg, foreground=text)

        self.style.configure("Card.TFrame", background=panel, relief="flat")
        self.style.configure("CardInner.TFrame", background=panel)
        self.style.configure("SectionHeading.TLabel", background=panel, foreground=primary, font=("Segoe UI", 12, "bold"))
        self.style.configure("FieldLabel.TLabel", background=panel, foreground=muted, font=("Segoe UI", 10, "bold"))
        self.style.configure("Subtle.TLabel", background=panel, foreground=muted)
        self.style.configure("Info.TLabel", background=panel, foreground=text, font=("Segoe UI", 10))

        self.style.configure("Primary.TButton", background=primary, foreground="#ffffff", padding=(14, 8))
        self.style.map(
            "Primary.TButton",
            background=[("disabled", border), ("active", primary_dark)],
            foreground=[("disabled", muted)],
        )
        self.style.configure("Accent.TButton", background=accent, foreground="#ffffff", padding=(14, 8))
        self.style.map(
            "Accent.TButton",
            background=[("disabled", border), ("active", theme.get("accentActive", accent))],
            foreground=[("disabled", muted)],
        )
        self.style.configure("Ghost.TButton", background=panel, foreground=primary, padding=(12, 6))
        self.style.map(
            "Ghost.TButton",
            background=[("active", theme.get("ghostActive", border))],
            foreground=[("disabled", muted)],
        )

        self.style.configure("Toggle.TCheckbutton", background=panel, foreground=text)
        self.style.configure("Segment.TRadiobutton", background=panel, foreground=text, padding=(8, 2))

        self.style.configure(
            "StatusBar.TLabel",
            background=theme.get("statusBg", panel),
            foreground=muted,
            padding=(12, 6),
        )

        self.style.configure("Treeview", background=panel, fieldbackground=panel, foreground=text, bordercolor=border)
        self.style.configure("Treeview.Heading", background=panel, foreground=text)

        self.style.configure("TNotebook", background=panel, tabmargins=(8, 4, 8, 0))
        self.style.configure("TNotebook.Tab", background=panel, foreground=muted, padding=(14, 8))
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", bg)],
            foreground=[("selected", text)],
        )

        self.style.configure(
            "Hero.Horizontal.TProgressbar",
            background=primary,
            troughcolor=theme.get("progressTrough", border),
            bordercolor=panel,
            lightcolor=primary,
            darkcolor=primary_dark,
        )

    def _apply_theme_classic_widgets(self) -> None:
        theme = self.theme
        try:
            self.root.configure(bg=theme.get("bg", "#f2f2f2"))
        except tk.TclError:
            pass

        classic_widgets = [self.txt, self.canvas]
        for widget in classic_widgets:
            try:
                widget.configure(bg=theme.get("panel", theme.get("bg", "#f2f2f2")), fg=theme.get("text", "#333740"))
            except tk.TclError:
                widget.configure(bg=theme.get("bg", "#f2f2f2"))

        self.canvas.configure(highlightthickness=0)

    def _apply_hero_theme(self) -> None:
        theme = self.theme
        hero_bg = theme.get("heroBg", theme.get("primary", "#1740b1"))
        hero_text = theme.get("heroText", "#ffffff")
        hero_muted = theme.get("heroMuted", "#d6e0ff")
        badge_bg = theme.get("heroBadgeBg", theme.get("accent", "#ff7f32"))
        badge_text = theme.get("heroBadgeText", "#ffffff")
        accent = theme.get("accent", "#ff7f32")

        for widget in (self.hero, self.hero_content):
            widget.configure(bg=hero_bg)
        self.hero_accent.configure(bg=accent)
        self.hero_title.configure(bg=hero_bg, fg=hero_text)
        self.hero_subtitle.configure(bg=hero_bg, fg=hero_muted)
        self.hero_badge.configure(bg=badge_bg, fg=badge_text)

    def toggle_theme(self) -> None:
        self.theme_mode = "dark" if self.theme_mode == "light" else "light"
        self.theme = self.theme_doc.get(self.theme_mode, self.theme_doc.get("light", {}))
        self._apply_theme()
        self._apply_theme_classic_widgets()
        self._apply_hero_theme()
        self.theme_doc["last_mode"] = self.theme_mode
        save_theme_document(self.theme_doc)
        self.status.configure(text=f"Theme set to {self.theme_mode} mode")

    def _refresh_format_lengths(self) -> None:
        lengths: dict[int, list[str]] = {}
        for fmt in self.formats.values():
            lengths.setdefault(fmt.bit_length, []).append(fmt.name)
        for names in lengths.values():
            names.sort()
        self.format_length_lookup = lengths
        self.format_bit_lengths = sorted(lengths.keys())
        if hasattr(self, "input_var"):
            self._update_input_feedback()

    def _nearest_bit_length(self, bit_length: int) -> tuple[int | None, list[str]]:
        if not self.format_bit_lengths or bit_length <= 0:
            return None, []
        nearest = min(self.format_bit_lengths, key=lambda target: abs(target - bit_length))
        return nearest, self.format_length_lookup.get(nearest, [])

    def _update_input_feedback(self) -> None:
        if not hasattr(self, "input_var"):
            return
        raw_value = self.input_var.get()
        cleaned = clean_input(raw_value)
        condensed = cleaned.replace(" ", "").replace("-", "").replace("_", "")
        if condensed.startswith(("0x", "0X")):
            condensed = condensed[2:]

        if not condensed:
            self.input_feedback.configure(text="Waiting for input…", style="Info.TLabel")
            self.bit_progress.configure(value=0)
            self.bit_progress_label.configure(text="")
            return

        if is_binary(condensed):
            detected_type = "Binary"
            bit_length = len(condensed)
        elif is_hex(condensed):
            detected_type = "Hexadecimal"
            bit_length = len(condensed) * 4
        else:
            self.input_feedback.configure(
                text="Input contains characters outside binary/hex ranges. Only 0-1 or 0-9/A-F are supported.",
                style="Info.TLabel",
            )
            self.bit_progress.configure(value=0)
            self.bit_progress_label.configure(text="")
            return

        nearest, names = self._nearest_bit_length(bit_length)
        if nearest:
            percent = max(0, min(100, int((bit_length / nearest) * 100))) if nearest else 0
            self.bit_progress.configure(value=percent)
            format_hint = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
            if percent == 100:
                status = f"Perfect match for {nearest}-bit formats: {format_hint or 'multiple entries'}"
            else:
                status = (
                    f"{bit_length} bits detected • Closest catalogued format: {nearest} bits "
                    f"({format_hint or 'see formats list'})"
                )
            self.bit_progress_label.configure(text=status)
        else:
            self.bit_progress.configure(value=0)
            self.bit_progress_label.configure(text=f"{bit_length} bits detected")

        display_text = f"Detected {detected_type} payload • {bit_length} bits"
        if detected_type == "Hexadecimal":
            display_text += " • Converted to binary automatically"
        self.input_feedback.configure(text=display_text, style="Info.TLabel")

    def paste_from_clipboard(self) -> None:
        try:
            clipboard = self.root.clipboard_get()
        except tk.TclError:
            clipboard = ""
        if clipboard:
            self.input_var.set(clipboard)
            self.input_entry.icursor(tk.END)
            self.input_entry.focus_set()
            self.status.configure(text="Payload pasted from clipboard")
        else:
            self.status.configure(text="Clipboard is empty or unavailable")

    def clear_input(self) -> None:
        self.input_var.set("")
        self.input_entry.focus_set()
        self.status.configure(text="Input cleared")

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
        self._refresh_format_lengths()
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
        messagebox.showinfo("Export", f"Formats exported to {path}")

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

        btn_add = ttk.Button(frame, text="Add", command=lambda: self._edit_format(win, None, tree))
        btn_add.grid(row=1, column=0, sticky=tk.W, pady=6)

        btn_edit = ttk.Button(
            frame,
            text="Edit",
            command=lambda: self._edit_format(win, self._selected_format(tree), tree),
        )
        btn_edit.grid(row=1, column=1, sticky=tk.W, pady=6)

        btn_clone = ttk.Button(frame, text="Clone", command=lambda: self._clone_selected_format(tree))
        btn_clone.grid(row=1, column=2, sticky=tk.W, pady=6)

        btn_delete = ttk.Button(frame, text="Delete", command=lambda: self._delete_selected_format(tree))
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
            self._refresh_format_lengths()
            tree.delete(item)
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
        self._refresh_format_lengths()
        tree.insert("", tk.END, values=(clone.get("name"), clone.get("bit_length")))
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

        fields_frame = ttk.Labelframe(body, text="Fields (contiguous ranges)")
        fields_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=6)
        fields_tree = ttk.Treeview(fields_frame, columns=("Name", "Start", "End"), show="headings", height=6)
        for column in ("Name", "Start", "End"):
            fields_tree.heading(column, text=column)
            fields_tree.column(column, anchor=tk.W, width=120)
        fields_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        ttk.Button(fields_frame, text="Add Field", command=lambda: self._add_field_row(fields_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(fields_frame, text="Edit Field", command=lambda: self._edit_field_row(fields_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(fields_frame, text="Delete Field", command=lambda: self._del_field_row(fields_tree)).grid(row=1, column=2, pady=4)

        parity_frame = ttk.Labelframe(body, text="Parity rules")
        parity_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        parity_tree = ttk.Treeview(parity_frame, columns=("Type", "Start", "End"), show="headings", height=5)
        for column in ("Type", "Start", "End"):
            parity_tree.heading(column, text=column)
            parity_tree.column(column, anchor=tk.W, width=120)
        parity_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        ttk.Button(parity_frame, text="Add Rule", command=lambda: self._add_parity_row(parity_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(parity_frame, text="Edit Rule", command=lambda: self._edit_parity_row(parity_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(parity_frame, text="Delete Rule", command=lambda: self._del_parity_row(parity_tree)).grid(row=1, column=2, pady=4)

        if fmt:
            for field in fmt.get("fields", []):
                fields_tree.insert("", tk.END, values=(field.get("name"), field.get("start"), field.get("end")))
            for rule in fmt.get("parity", []):
                rule_type = rule.get("type", "even").lower()
                for rng in rule.get("ranges", []):
                    parity_tree.insert("", tk.END, values=(rule_type, rng.get("start"), rng.get("end")))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=8)
        ttk.Button(
            actions,
            text="Save",
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
        ttk.Button(actions, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=8)

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
            tree.delete(item)

    def _field_edit_dialog(self, tree: ttk.Treeview, row) -> None:
        win = tk.Toplevel(self.root)
        win.title("Field")
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Name").grid(row=0, column=0, sticky=tk.W)
        name_var = tk.StringVar(value=row[1][0] if row else "")
        ttk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(frame, text="Start").grid(row=1, column=0, sticky=tk.W)
        start_var = tk.StringVar(value=row[1][1] if row else "0")
        ttk.Entry(frame, textvariable=start_var, width=8).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(frame, text="End").grid(row=2, column=0, sticky=tk.W)
        end_var = tk.StringVar(value=row[1][2] if row else "1")
        ttk.Entry(frame, textvariable=end_var, width=8).grid(row=2, column=1, sticky=tk.W)

        def save_row() -> None:
            try:
                start = int(start_var.get())
                end = int(end_var.get())
                if end <= start:
                    messagebox.showerror("Field", "End must be > Start")
                    return
            except ValueError:
                messagebox.showerror("Field", "Start/End must be integers")
                return
            values = (name_var.get(), start, end)
            if row:
                tree.item(row[0], values=values)
            else:
                tree.insert("", tk.END, values=values)
            win.destroy()

        ttk.Button(frame, text="Save", command=save_row).grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(frame, text="Cancel", command=win.destroy).grid(row=4, column=0, columnspan=2, pady=4)

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

        ttk.Button(frame, text="Save", command=save_rule).grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(frame, text="Cancel", command=win.destroy).grid(row=4, column=0, columnspan=2, pady=4)

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
        for item in fields_tree.get_children(""):
            fname, start, end = fields_tree.item(item, "values")
            fields.append({"name": fname, "start": int(start), "end": int(end)})

        parity = []
        for item in parity_tree.get_children(""):
            ptype, start, end = parity_tree.item(item, "values")
            parity.append({"type": ptype, "ranges": [{"start": int(start), "end": int(end)}]})

        entry = {"name": name, "bit_length": bitlen, "fields": fields, "parity": parity}

        if original and original in self.formats_doc.get("formats", []):
            idx = self.formats_doc["formats"].index(original)
            self.formats_doc["formats"][idx] = entry
        else:
            self.formats_doc.setdefault("formats", []).append(entry)

        self.format_repo.update(self.formats_doc)
        self.formats = self.format_repo.formats
        self._refresh_format_lengths()

        listing.delete(*listing.get_children(""))
        for fmt in self.formats_doc.get("formats", []):
            listing.insert("", tk.END, values=(fmt.get("name"), fmt.get("bit_length")))

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

        ttk.Button(frame, text="Run", command=run_test).grid(row=5, column=0, pady=6)
        ttk.Button(frame, text="Close", command=win.destroy).grid(row=5, column=1, pady=6)

        win.wait_window()

    # ---------------- Calculate / Render ----------------
    def on_calculate(self) -> None:
        input_data = self.input_entry.get()
        binary_string, error = process_input(input_data)
        if error:
            messagebox.showerror("Error", error)
            return
        self.last_binary_used = binary_string
        self.txt.delete("1.0", tk.END)
        self.txt.insert(
            tk.END,
            f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n",
        )

        exact, compatible = self._detect_formats(binary_string)
        if not exact and not compatible:
            self.txt.insert(tk.END, "No matching formats found.\n")
            self.status.configure(
                text=f"Analyzed {len(binary_string)} bits • No matching formats"
            )
            return

        self.last_rows_for_csv = []
        self.tree.delete(*self.tree.get_children(""))
        self.last_format_checks = []

        rendered_any = False
        if exact:
            self.txt.insert(tk.END, "== Exact bit-length matches ==\n")
            rendered_any |= self._render_candidates(binary_string, exact, slice_mode=None)

        if compatible:
            self.txt.insert(tk.END, "== Compatible (input longer than known format) ==\n")
            self.txt.insert(tk.END, "These may indicate framing/padding.\n\n")
            rendered_any |= self._render_candidates(
                binary_string,
                compatible,
                slice_mode=self.slice_mode.get(),
            )

        if not rendered_any:
            self.txt.insert(
                tk.END,
                "No formats passed parity in strict mode.\nTip: Enable 'Show parity failures (diagnostic)' to inspect candidates.\n",
            )

        self._draw_parity_visualizer()
        total_matches = len(exact) + len(compatible)
        match_text = "format" if total_matches == 1 else "formats"
        self.status.configure(
            text=f"Analyzed {len(binary_string)} bits • {total_matches} matching {match_text}"
        )

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

    def _render_candidates(self, binary_string: str, candidates: list[tuple], slice_mode: str | None) -> bool:
        rendered = False
        for name, fmt in candidates:
            bit_length = fmt.bit_length
            if slice_mode is None:
                use_bits = binary_string
                display_name = name
            else:
                use_bits = binary_string[:bit_length] if slice_mode == "left" else binary_string[-bit_length:]
                display_name = name + (" (leftmost)" if slice_mode == "left" else " (rightmost)")
            if not self.show_fails.get() and not self._parity_all_ok(use_bits, fmt):
                continue
            self._render_format(use_bits, display_name, fmt)
            rendered = True
        return rendered

    def _render_format(self, binary_string: str, name: str, fmt: NormalizedFormat) -> None:
        self.txt.insert(tk.END, f"Format: {name}\n")
        fields = extract_fields(binary_string, fmt)
        for field, meta in fields.items():
            self.txt.insert(
                tk.END,
                f"  {field:14}: {meta['int']} (hex {meta['hex']}), bits[{meta['len']}]={meta['bits']}\n",
            )
            start, end = meta["range"]
            self.tree.insert("", tk.END, values=(field, f"{start}–{end}", meta["int"], meta["hex"]))
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
                self.txt.insert(
                    tk.END,
                    f"  Parity {result['type']:4} {result['coverage'][0]}–{result['coverage'][1]}: {status} "
                    f"(expected {result['expected']}, actual {result['actual']}; data_len={result['data_len']})\n",
                )
            self.last_format_checks = parity
        self.txt.insert(tk.END, "\n")

    def _parity_all_ok(self, binary_string: str, fmt: NormalizedFormat) -> bool:
        parity = verify_parity(binary_string, fmt)
        if not parity:
            return True
        return all(result.get("ok", True) for result in parity)

    # ---------------- Visualizer ----------------
    def _draw_parity_visualizer(self) -> None:
        self.canvas.delete("all")
        if not self.last_binary_used:
            return
        width = self.canvas.winfo_width() or self.canvas.winfo_reqwidth()
        height = self.canvas.winfo_height() or 60
        total = len(self.last_binary_used)
        mid = height // 2
        self.canvas.create_line(10, mid, width - 10, mid, fill="#4b6cff", width=4)
        for result in self.last_format_checks:
            start, end = result["coverage"]
            x1 = 10 + (width - 20) * (start / total)
            x2 = 10 + (width - 20) * (end / total)
            color = "#00adff" if result["type"] == "even" else "#75e600"
            self.canvas.create_rectangle(x1, mid - 10, x2, mid + 10, fill=color, outline="")
            if result["ok"] is False:
                self.canvas.create_rectangle(x1, mid - 10, x2, mid + 10, fill="#ff4d4f", outline="", stipple="gray25")

    # ---------------- Copy / Export ----------------
    def copy_results(self) -> None:
        text = self.txt.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.configure(text="Results copied to clipboard")

    def copy_selected_table(self) -> None:
        selected = self.tree.focus()
        if not selected:
            self.status.configure(text="Select a table row to copy")
            return
        values = self.tree.item(selected, "values")
        copy_text = "\t".join(str(value) for value in values)
        self.root.clipboard_clear()
        self.root.clipboard_append(copy_text)
        self.status.configure(text="Selected row copied to clipboard")

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
        messagebox.showinfo("Exported", f"Saved to {path}")


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
        root = tk.Tk()
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
