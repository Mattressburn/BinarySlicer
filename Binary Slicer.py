#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BinarySlicer – JCI Edition (fixed, ready-to-run)
- Tkinter GUI for parsing HID/Wiegand-like binary/hex payloads
- External formats.json (contiguous ranges + parity rules) with bootstrap defaults
- Light/Dark theme toggle using ttk.Style (clam theme)
- Manage Formats dialog (Add/Edit/Delete/Clone, Import/Export, Self-test)
- Compact table view with per-row copy
- Parity visualizer bar
- Crash-safe main() with logging to %LOCALAPPDATA%\BinarySlicer\logs.txt

Notes
- No bit permutations (contiguous only) per your request
- CSN switches (endianness/byte order/BCD) can be extended in decode step if needed
"""

from __future__ import annotations
import os, sys, json, csv, textwrap, re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --------------------- Bootstrap defaults so the app never silently exits ---------------------
DEFAULT_THEME = {
    "schema_version": 1,
    "theme_pack_version": "2025.10.15",
    "light": {
        "bg": "#f2f2f2",
        "panel": "#ffffff",
        "text": "#333740",
        "mutedText": "#5a5f6b",
        "primary": "#1740b1",
        "primaryDark": "#000070",
        "accent": "#00adff",
        "success": "#75e600",
        "border": "#e5e7eb",
        "shadow": "rgba(0,0,0,0.08)",
        "gradient": ["#000070", "#1740b1"]
    },

    # 🔻 REPLACE THIS ENTIRE DARK BLOCK WITH THE FOLLOWING
    "dark": {
        "bg": "#1e1e2e",          # deep neutral base
        "panel": "#2b2b3c",       # slightly lighter for contrast
        "text": "#dcdfe4",        # main text
        "mutedText": "#a4acc4",   # secondary info
        "primary": "#00bcd4",     # JCI teal accent
        "primaryDark": "#008394",
        "accent": "#9d7dff",      # purple highlight
        "success": "#80e27e",     # green for valid parity
        "border": "#3a3f55",      # soft divider
        "shadow": "rgba(0,0,0,0.45)",
        "gradient": ["#00bcd4", "#0064ff"]
    }
}


DEFAULT_FORMATS = {
    "schema_version": 1,
    "format_pack_version": "2025.10.15",
    "formats": [
        {
            "name": "H10301 - 26-bit",
            "bit_length": 26,
            "fields": [
                {"name":"Parity L", "start":0, "end":0, "role":"parity"},
                {"name":"Facility", "start":1, "end":8},
                {"name":"Card", "start":9, "end":24},
                {"name":"Parity R", "start":25, "end":25, "role":"parity"}
            ],
            "parity": [
                {"type":"even", "ranges":[{"start":1,"end":12}]},
                {"type":"odd",  "ranges":[{"start":13,"end":24}]}
            ],
            "csn": {"enabled": False}
        },
        {
            "name": "H10306 - 34-bit",
            "bit_length": 34,
            "fields": [
                {"name":"Parity L","start":0,"end":0,"role":"parity"},
                {"name":"Facility","start":1,"end":16},
                {"name":"Card","start":17,"end":32},
                {"name":"Parity R","start":33,"end":33,"role":"parity"}
            ],
            "parity":[
                {"type":"even","ranges":[{"start":1,"end":16}]},
                {"type":"odd","ranges":[{"start":17,"end":32}]}
            ],
            "csn":{"enabled": False}
        },
        {
            "name": "H10302 - 37-bit",
            "bit_length": 37,
            "fields": [
                {"name":"Parity L","start":0,"end":0,"role":"parity"},
                {"name":"Facility","start":1,"end":16},
                {"name":"Card","start":17,"end":35},
                {"name":"Parity R","start":36,"end":36,"role":"parity"}
            ],
            "parity":[
                {"type":"even","ranges":[{"start":1,"end":18}]},
                {"type":"odd","ranges":[{"start":19,"end":35}]}
            ],
            "csn":{"enabled": False}
        },
        {
            "name": "P10001 - 40-bit (Honeywell)",
            "bit_length": 40,
            "fields": [
                {"name":"Parity L","start":0,"end":0,"role":"parity"},
                {"name":"Facility","start":1,"end":16},
                {"name":"Card","start":17,"end":38},
                {"name":"Parity R","start":39,"end":39,"role":"parity"}
            ],
            "parity":[
                {"type":"even","ranges":[{"start":1,"end":19}]},
                {"type":"odd","ranges":[{"start":20,"end":38}]}
            ],
            "csn":{"enabled": False}
        },
        {
            "name": "CSN - 32-bit (4-byte)",
            "bit_length": 32,
            "fields": [ {"name":"CSN","start":0,"end":31,"view":["int","hex"]} ],
            "parity":[],
            "csn":{"enabled": True, "bit_order":"MSB", "byte_order":"big", "bcd": False}
        },
        {
            "name": "CSN - 56-bit (7-byte)",
            "bit_length": 56,
            "fields": [ {"name":"CSN","start":0,"end":55,"view":["int","hex"]} ],
            "parity":[],
            "csn":{"enabled": True, "bit_order":"MSB", "byte_order":"big", "bcd": False}
        },
        {
            "name": "CSN - 64-bit (8-byte, TWIC/CAC friendly)",
            "bit_length": 64,
            "fields": [ {"name":"CSN","start":0,"end":63,"view":["int","hex","bcd"]} ],
            "parity":[],
            "csn":{"enabled": True, "bit_order":"MSB", "byte_order":"big", "bcd": True}
        }
    ]
}

# --------------------- Import helper modules with graceful fallbacks ---------------------
try:
    from modules.paths import config_path, appdata_dir
    from modules.theme import load_theme
    from modules.formats_io import load_formats, save_formats, merge_formats
except Exception:
    # Fallbacks (portable first, then AppData) so app runs even if modules/ missing
    def _app_dir():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    def appdata_dir():
        return os.path.join(os.getenv("APPDATA", _app_dir()), "BinarySlicer")
    def config_path(name: str) -> str:
        portable = os.path.join(_app_dir(), "config", name)
        if os.path.exists(portable):
            return portable
        return os.path.join(appdata_dir(), name)
    def load_theme(mode: str = "light"):
        try:
            with open(config_path("theme.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(mode, data.get("light", {}))
        except Exception:
            return DEFAULT_THEME[mode] if mode in DEFAULT_THEME else DEFAULT_THEME["light"]
    def _read_json_safe(path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    def load_formats():
        return _read_json_safe(config_path("formats.json"), DEFAULT_FORMATS)
    def save_formats(doc: dict):
        p = config_path("formats.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            if os.path.exists(p):
                os.replace(p, p + ".bak")
        except Exception:
            pass
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
    def merge_formats(base: dict, incoming: dict):
        names = {f.get("name"): i for i, f in enumerate(base.get("formats", []))}
        for f in incoming.get("formats", []):
            nm = f.get("name")
            if nm in names:
                base["formats"][names[nm]] = f
            else:
                base["formats"].append(f)
        return base

# --------------------- Utility ---------------------
HEX_CHARS = set("0123456789abcdefABCDEF")

def clean_input(s: str) -> str:
    return s.strip()

def is_binary(s: str) -> bool:
    return all(ch in '01' for ch in s) and len(s) > 0

def is_hex(s: str) -> bool:
    return all(ch in HEX_CHARS for ch in s) and len(s) > 0

def hex_to_binary(hex_string: str) -> str | None:
    try:
        return bin(int(hex_string, 16))[2:].zfill(len(hex_string) * 4)
    except ValueError:
        return None

def process_input(input_string: str):
    s = clean_input(input_string)
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    if s.startswith(("0x", "0X")):
        s = s[2:]
    if is_binary(s):
        return s, None
    if is_hex(s):
        b = hex_to_binary(s)
        if b is None:
            return None, "Invalid hex input."
        return b, None
    return None, "Input must be hex or binary (e.g., 0x1A2B, 1100101)."

def format_binary_groups(b: str, group: int = 4) -> str:
    if group <= 0:
        return b
    rem = len(b) % group
    leading = '' if rem == 0 else b[:rem] + ' '
    rest = b[rem:]
    return leading + ' '.join(textwrap.wrap(rest, group)) if rest else b

# --------------------- Decoding core ---------------------

def extract_bits(binary_string: str, start: int, end: int) -> str:
    """Inclusive end index extraction (0-based)."""
    return binary_string[start:end+1]

def bits_to_int(bits: str) -> int:
    return int(bits, 2) if bits else 0

def extract_fields(binary_string: str, fmt_obj: dict):
    fields = {}
    for field, (start, end) in fmt_obj["fields"].items():
        bits = extract_bits(binary_string, start, end)
        fields[field] = {
            "bits": bits,
            "int": bits_to_int(bits),
            "hex": f"0x{bits_to_int(bits):X}",
            "len": (end - start + 1),
            "range": (start, end),
        }
    return fields

def parity_even_bit_needed(bits: str) -> int:
    ones = bits.count('1')
    return 0 if ones % 2 == 0 else 1

def parity_odd_bit_needed(bits: str) -> int:
    ones = bits.count('1')
    return 1 if ones % 2 == 0 else 0

def verify_parity(binary_string: str, fmt_obj: dict):
    result = []
    coverage = fmt_obj.get("parity_coverage")
    if not coverage:
        return result
    if isinstance(coverage, dict):
        rules = []
        for typ in ("even", "odd"):
            if typ in coverage:
                rules.append({"type": typ, "ranges": [coverage[typ]]})
    else:
        rules = coverage
    for rule in rules:
        typ = rule.get("type", "even").lower()
        for (s,e) in rule.get("ranges", []):
            data_bits = extract_bits(binary_string, s, e)
            expected = parity_even_bit_needed(data_bits) if typ == "even" else parity_odd_bit_needed(data_bits)
            result.append({
                "label": "Even Parity" if typ=="even" else "Odd Parity",
                "type": typ,
                "coverage": (s,e),
                "expected": expected,
                "actual": None,   # could be wired to a named parity field if present
                "ok": None,       # leave as None (diagnostic) unless mapped to a parity bit
                "data_len": len(data_bits),
            })
    return result

# --------------------- App ---------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("BinarySlicer – JCI Edition")

        # Theme
        self.theme_mode = "light"
        self.theme = load_theme(self.theme_mode)
        self._init_styles()
        self._apply_theme()

        # Load formats JSON and normalize
        self.formats_doc = load_formats()
        self.FORMATS = self._normalize_formats(self.formats_doc)

        # Layout
        container = ttk.Frame(root, padding=10)
        container.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        ttk.Label(container, text="Enter Hex or Binary:").grid(row=0, column=0, sticky=tk.W)
        self.input_entry = ttk.Entry(container, width=64)
        self.input_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))
        container.columnconfigure(1, weight=1)

        self.btn_calc = ttk.Button(container, text="Calculate", command=self.on_calculate)
        self.btn_calc.grid(row=0, column=2, padx=6)
        self.btn_copy = ttk.Button(container, text="Copy Results", command=self.copy_results)
        self.btn_copy.grid(row=0, column=3, padx=6)
        self.btn_export = ttk.Button(container, text="Export CSV", command=self.export_csv)
        self.btn_export.grid(row=0, column=4, padx=6)

        self.show_fails = tk.BooleanVar(value=False)
        ttk.Checkbutton(container, text="Show parity failures (diagnostic)", variable=self.show_fails).grid(row=0, column=5, padx=6)

        ttk.Label(container, text="Compatible slicing:").grid(row=0, column=6, padx=(12, 2))
        self.slice_mode = tk.StringVar(value="left")
        ttk.Radiobutton(container, text="Leftmost", value="left", variable=self.slice_mode).grid(row=0, column=7, padx=2)
        ttk.Radiobutton(container, text="Rightmost", value="right", variable=self.slice_mode).grid(row=0, column=8, padx=2)

        self.btn_theme = ttk.Button(container, text="Toggle Theme", command=self.toggle_theme)
        self.btn_theme.grid(row=0, column=9, padx=6)

        # Notebook
        self.nb = ttk.Notebook(container)
        self.nb.grid(row=1, column=0, columnspan=10, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(8,0))
        container.rowconfigure(1, weight=1)

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
        self.tree = ttk.Treeview(self.tab_table, columns=cols, show='headings')
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, stretch=True, anchor=tk.W, width=120)
        self.tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.tab_table.rowconfigure(0, weight=1)
        self.tab_table.columnconfigure(0, weight=1)
        self.copy_table_btn = ttk.Button(self.tab_table, text="Copy Selected", command=self.copy_selected_table)
        self.copy_table_btn.grid(row=1, column=0, sticky=tk.W, pady=6)

        # Visualizer canvas
        self.canvas = tk.Canvas(self.tab_visual, height=60)
        self.canvas.grid(row=0, column=0, sticky=(tk.E, tk.W), padx=4, pady=8)
        self.tab_visual.columnconfigure(0, weight=1)

        # Status
        self.status = ttk.Label(container, text=f"Formats loaded: {len(self.FORMATS)} | AppData: {appdata_dir()}")
        self.status.grid(row=2, column=0, columnspan=10, sticky=(tk.W, tk.E), pady=(8,0))

        # Menu
        self._build_menu()

        self.last_rows_for_csv = []
        self.last_binary_used = ''
        self.last_format_checks = []

        # Apply theme to classic widgets
        self._apply_theme_classic_widgets()

    # ---------------- Theme helpers ----------------
    def _init_styles(self):
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
            

    def _apply_theme(self):
        T = self.theme
        # Base ttk styles
        self.style.configure(".", font=("Consolas", 10))
        self.root.configure(bg=T.get("bg", "#f2f2f2"))
        self.style.configure("TFrame", background=T.get("bg"))
        self.style.configure("TLabelframe", background=T.get("bg"))
        self.style.configure("TLabelframe.Label", background=T.get("bg"), foreground=T.get("text", "#333740"))
        self.style.configure("TLabel", background=T.get("bg"), foreground=T.get("text", "#333740"))
        self.style.configure("TCheckbutton", background=T.get("bg"), foreground=T.get("text", "#333740"))
        self.style.configure("TRadiobutton", background=T.get("bg"), foreground=T.get("text", "#333740"))
        self.style.configure("TNotebook", background=T.get("bg"))
        self.style.configure("TNotebook.Tab", background=T.get("panel", T.get("bg")), foreground=T.get("text", "#333740"))
        self.style.map("TNotebook.Tab", background=[("selected", T.get("panel", T.get("bg")))], foreground=[("selected", T.get("text", "#333740"))])
        panel = T.get("panel", T.get("bg"))
        self.style.configure("Treeview", background=panel, fieldbackground=panel, foreground=T.get("text", "#333740"))
        self.style.configure("Treeview.Heading", background=panel, foreground=T.get("text", "#333740"))
        self.style.configure("TButton", padding=6)
        self.style.map("TButton", relief=[("pressed", "sunken"), ("active", "raised")])
                # --- Treeview striping & selection polish ---
        style = self.style
        T = self.theme
        panel = T.get("panel", "#2b2b3c")
        accent = T.get("primary", "#00bcd4")
        muted = T.get("mutedText", "#a4acc4")
        border = T.get("border", "#3a3f55")

        # base colors
        style.configure(
            "Treeview",
            background=panel,
            fieldbackground=panel,
            foreground=T.get("text", "#dcdfe4"),
            bordercolor=border,
            borderwidth=1,
            rowheight=22,
        )

        style.configure(
            "Treeview.Heading",
            background=panel,
            foreground=T.get("text", "#dcdfe4"),
            relief="flat",
            borderwidth=0,
        )

        # selection + hover effects
        style.map(
            "Treeview",
            background=[
                ("selected", accent),
                ("!selected", panel),
                ("active", "#3a3f55")
            ],
            foreground=[
                ("selected", "#ffffff"),
                ("!selected", T.get("text", "#dcdfe4"))
            ],
            highlightcolor=[("focus", accent)],
        )

        # zebra striping every other row
        try:
            for i, row in enumerate(self.table.get_children()):
                bg = panel if i % 2 == 0 else "#242432"
                self.table.tag_configure(f"row_{i}", background=bg)
                self.table.item(row, tags=(f"row_{i}",))
        except Exception:
            # safe to skip if table not yet populated
            pass


    def _apply_theme_classic_widgets(self):
        # Apply to Text/Canvas which aren't themed by ttk
        T = self.theme
        if hasattr(self, 'txt') and self.txt:
            try:
                self.txt.configure(bg=T.get("panel", T.get("bg")), fg=T.get("text", "#333740"), insertbackground=T.get("text", "#333740"))
            except tk.TclError:
                pass
        if hasattr(self, 'canvas') and self.canvas:
            try:
                self.canvas.configure(bg=T.get("panel", T.get("bg")))
            except tk.TclError:
                pass

    def toggle_theme(self):
        self.theme_mode = "dark" if self.theme_mode == "light" else "light"
        self.theme = load_theme(self.theme_mode)
        self._apply_theme()
        self._apply_theme_classic_widgets()

    # ---------------- Menu / Manage Formats ----------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        fm = tk.Menu(menubar, tearoff=False)
        fm.add_command(label="Manage Formats…", command=self.manage_formats_dialog)
        fm.add_separator()
        fm.add_command(label="Import formats JSON…", command=self.menu_import)
        fm.add_command(label="Export current formats…", command=self.menu_export)
        menubar.add_cascade(label="Formats", menu=fm)

    def menu_import(self):
        path = filedialog.askopenfilename(title="Import formats JSON", filetypes=[("JSON","*.json"),("All","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming = json.load(f)
            self.formats_doc = merge_formats(self.formats_doc, incoming)
            save_formats(self.formats_doc)
            self.FORMATS = self._normalize_formats(self.formats_doc)
            messagebox.showinfo("Imported", f"Merged formats from {os.path.basename(path)}")
            self.status.configure(text=f"Formats loaded: {len(self.FORMATS)} (merged)")
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def menu_export(self):
        default_name = f"formats_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=default_name,
                                            filetypes=[("JSON","*.json"),("All","*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.formats_doc, f, indent=2)
            messagebox.showinfo("Exported", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def manage_formats_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Manage Formats")
        dlg.geometry("900x520")
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Left: list
        left = ttk.Frame(frm)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cols = ("Name","Bits")
        tree = ttk.Treeview(left, columns=cols, show='headings', height=16)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, anchor=tk.W, stretch=True)
        tree.pack(fill=tk.BOTH, expand=True)

        btnbar = ttk.Frame(left)
        btnbar.pack(fill=tk.X, pady=6)
        ttk.Button(btnbar, text="Add", command=lambda: self._edit_format(dlg, None, tree)).pack(side=tk.LEFT, padx=3)
        ttk.Button(btnbar, text="Edit", command=lambda: self._edit_selected_format(dlg, tree)).pack(side=tk.LEFT, padx=3)
        ttk.Button(btnbar, text="Delete", command=lambda: self._delete_selected_format(tree)).pack(side=tk.LEFT, padx=3)
        ttk.Button(btnbar, text="Clone", command=lambda: self._clone_selected_format(tree)).pack(side=tk.LEFT, padx=3)

        # Right: self-test area
        right = ttk.Frame(frm)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        ttk.Label(right, text="Self-test (paste Hex or Binary)").pack(anchor=tk.W)
        test_entry = tk.Text(right, height=5)
        test_entry.pack(fill=tk.X)
        ttk.Button(right, text="Run Test", command=lambda: self._self_test(tree, test_entry, right)).pack(anchor=tk.W, pady=6)

        test_out = tk.Text(right, height=12)
        test_out.pack(fill=tk.BOTH, expand=True)
        test_out.configure(state=tk.DISABLED)

        # Populate list
        for f in self.formats_doc.get("formats", []):
            tree.insert('', tk.END, values=(f.get("name","?"), f.get("bit_length","?")))

        # retain refs
        self._manage_widgets = {"tree": tree, "test_out": test_out}

    def _edit_selected_format(self, dlg, tree):
        item = tree.focus()
        if not item:
            return
        name = tree.item(item, 'values')[0]
        fmt = next((f for f in self.formats_doc["formats"] if f.get("name")==name), None)
        if fmt:
            self._edit_format(dlg, fmt, tree)

    def _delete_selected_format(self, tree):
        item = tree.focus()
        if not item:
            return
        name = tree.item(item, 'values')[0]
        if messagebox.askyesno("Delete", f"Delete format '{name}'?"):
            self.formats_doc["formats"] = [f for f in self.formats_doc["formats"] if f.get("name")!=name]
            save_formats(self.formats_doc)
            self.FORMATS = self._normalize_formats(self.formats_doc)
            tree.delete(item)
            self.status.configure(text=f"Formats loaded: {len(self.FORMATS)} (deleted '{name}')")

    def _clone_selected_format(self, tree):
        item = tree.focus()
        if not item:
            return
        name = tree.item(item, 'values')[0]
        src = next((f for f in self.formats_doc["formats"] if f.get("name")==name), None)
        if not src:
            return
        dup = json.loads(json.dumps(src))
        dup["name"] = src.get("name","Format") + " (Copy)"
        self.formats_doc["formats"].append(dup)
        save_formats(self.formats_doc)
        self.FORMATS = self._normalize_formats(self.formats_doc)
        tree.insert('', tk.END, values=(dup.get("name"), dup.get("bit_length")))
        self.status.configure(text=f"Formats loaded: {len(self.FORMATS)} (cloned)")

    def _edit_format(self, parent, fmt, tree):
        win = tk.Toplevel(parent)
        win.title("Edit Format" if fmt else "Add Format")
        body = ttk.Frame(win, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Name").grid(row=0, column=0, sticky=tk.W)
        name_var = tk.StringVar(value=(fmt.get("name") if fmt else ""))
        ttk.Entry(body, textvariable=name_var, width=40).grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(body, text="Bit Length").grid(row=1, column=0, sticky=tk.W)
        bitlen_var = tk.StringVar(value=str(fmt.get("bit_length")) if fmt else "")
        ttk.Entry(body, textvariable=bitlen_var, width=12).grid(row=1, column=1, sticky=tk.W)

        fields_frame = ttk.Labelframe(body, text="Fields (contiguous ranges)")
        fields_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=6)
        fields_tree = ttk.Treeview(fields_frame, columns=("Name","Start","End"), show='headings', height=6)
        for c in ("Name","Start","End"):
            fields_tree.heading(c, text=c)
            fields_tree.column(c, anchor=tk.W, width=120)
        fields_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        ttk.Button(fields_frame, text="Add Field", command=lambda: self._add_field_row(fields_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(fields_frame, text="Edit Field", command=lambda: self._edit_field_row(fields_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(fields_frame, text="Delete Field", command=lambda: self._del_field_row(fields_tree)).grid(row=1, column=2, pady=4)

        parity_frame = ttk.Labelframe(body, text="Parity rules")
        parity_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        parity_tree = ttk.Treeview(parity_frame, columns=("Type","Start","End"), show='headings', height=5)
        for c in ("Type","Start","End"):
            parity_tree.heading(c, text=c)
            parity_tree.column(c, anchor=tk.W, width=120)
        parity_tree.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        ttk.Button(parity_frame, text="Add Rule", command=lambda: self._add_parity_row(parity_tree)).grid(row=1, column=0, pady=4)
        ttk.Button(parity_frame, text="Edit Rule", command=lambda: self._edit_parity_row(parity_tree)).grid(row=1, column=1, pady=4)
        ttk.Button(parity_frame, text="Delete Rule", command=lambda: self._del_parity_row(parity_tree)).grid(row=1, column=2, pady=4)

        if fmt:
            for f in fmt.get("fields", []):
                fields_tree.insert('', tk.END, values=(f.get("name"), f.get("start"), f.get("end")))
            for p in fmt.get("parity", []):
                typ = p.get("type","even").lower()
                for r in p.get("ranges", []):
                    parity_tree.insert('', tk.END, values=(typ, r.get("start"), r.get("end")))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=8)
        ttk.Button(actions, text="Save", command=lambda: self._save_format(win, fmt, name_var, bitlen_var, fields_tree, parity_tree, tree)).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=8)

    def _add_field_row(self, tv):
        self._field_edit_dialog(tv, None)
    def _edit_field_row(self, tv):
        item = tv.focus()
        if item:
            vals = tv.item(item, 'values')
            self._field_edit_dialog(tv, (item, vals))
    def _del_field_row(self, tv):
        item = tv.focus()
        if item: tv.delete(item)

    def _field_edit_dialog(self, tv, row):
        win = tk.Toplevel(self.root)
        win.title("Field")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Name").grid(row=0, column=0, sticky=tk.W)
        name = tk.StringVar(value=(row[1][0] if row else ""))
        ttk.Entry(frm, textvariable=name).grid(row=0, column=1, sticky=(tk.W, tk.E))
        ttk.Label(frm, text="Start").grid(row=1, column=0, sticky=tk.W)
        start = tk.StringVar(value=(row[1][1] if row else "0"))
        ttk.Entry(frm, textvariable=start, width=8).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(frm, text="End").grid(row=2, column=0, sticky=tk.W)
        end = tk.StringVar(value=(row[1][2] if row else "1"))
        ttk.Entry(frm, textvariable=end, width=8).grid(row=2, column=1, sticky=tk.W)
        def save_row():
            try:
                s = int(start.get()); e = int(end.get())
                if e <= s:
                    messagebox.showerror("Field", "End must be > Start")
                    return
            except Exception:
                messagebox.showerror("Field", "Start/End must be integers")
                return
            vals = (name.get(), s, e)
            if row:
                tv.item(row[0], values=vals)
            else:
                tv.insert('', tk.END, values=vals)
            win.destroy()
        ttk.Button(frm, text="Save", command=save_row).grid(row=3, column=1, sticky=tk.E, pady=6)

    def _add_parity_row(self, tv):
        self._parity_edit_dialog(tv, None)
    def _edit_parity_row(self, tv):
        item = tv.focus()
        if item:
            vals = tv.item(item, 'values')
            self._parity_edit_dialog(tv, (item, vals))
    def _del_parity_row(self, tv):
        item = tv.focus()
        if item: tv.delete(item)

    def _parity_edit_dialog(self, tv, row):
        win = tk.Toplevel(self.root)
        win.title("Parity Rule")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Type").grid(row=0, column=0, sticky=tk.W)
        typ = tk.StringVar(value=(row[1][0] if row else "even"))
        ttk.Combobox(frm, textvariable=typ, values=["even","odd"], state="readonly").grid(row=0, column=1, sticky=(tk.W, tk.E))
        ttk.Label(frm, text="Start").grid(row=1, column=0, sticky=tk.W)
        start = tk.StringVar(value=(row[1][1] if row else "1"))
        ttk.Entry(frm, textvariable=start, width=8).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(frm, text="End").grid(row=2, column=0, sticky=tk.W)
        end = tk.StringVar(value=(row[1][2] if row else "2"))
        ttk.Entry(frm, textvariable=end, width=8).grid(row=2, column=1, sticky=tk.W)
        def save_row():
            try:
                s = int(start.get()); e = int(end.get())
                if e <= s:
                    messagebox.showerror("Parity", "End must be > Start")
                    return
            except Exception:
                messagebox.showerror("Parity", "Start/End must be integers")
                return
            vals = (typ.get(), s, e)
            if row:
                tv.item(row[0], values=vals)
            else:
                tv.insert('', tk.END, values=vals)
            win.destroy()
        ttk.Button(frm, text="Save", command=save_row).grid(row=3, column=1, sticky=tk.E, pady=6)

    def _save_format(self, win, fmt, name_var, bitlen_var, fields_tree, parity_tree, list_tree):
        try:
            bit_length = int(bitlen_var.get())
        except Exception:
            messagebox.showerror("Format", "Bit Length must be an integer")
            return
        new_fmt = {
            "name": name_var.get().strip() or "Untitled",
            "bit_length": bit_length,
            "fields": [],
            "parity": []
        }
        for item in fields_tree.get_children(''):
            nm, s, e = fields_tree.item(item,'values')
            new_fmt["fields"].append({"name": nm, "start": int(s), "end": int(e)})
        parity_rules = {}
        for item in parity_tree.get_children(''):
            typ, s, e = parity_tree.item(item,'values')
            typ = str(typ).lower()
            parity_rules.setdefault(typ, []).append({"start": int(s), "end": int(e)})
        new_fmt["parity"] = [{"type": t, "ranges": rs} for t, rs in parity_rules.items()]

        if fmt:
            for i, f in enumerate(self.formats_doc["formats"]):
                if f.get("name") == fmt.get("name"):
                    self.formats_doc["formats"][i] = new_fmt
                    break
        else:
            self.formats_doc["formats"].append(new_fmt)

        save_formats(self.formats_doc)
        self.FORMATS = self._normalize_formats(self.formats_doc)
        list_tree.delete(*list_tree.get_children(''))
        for f in self.formats_doc.get("formats", []):
            list_tree.insert('', tk.END, values=(f.get("name","?"), f.get("bit_length","?")))
        self.status.configure(text=f"Formats loaded: {len(self.FORMATS)} (saved)")
        win.destroy()

    def _self_test(self, tree, test_entry, right_parent):
        content = test_entry.get("1.0", tk.END).strip()
        if not content:
            return
        bin_s, err = process_input(content)
        if err:
            messagebox.showerror("Self-test", err)
            return
        item = tree.focus()
        if not item:
            messagebox.showwarning("Self-test", "Select a format from the list first.")
            return
        name = tree.item(item, 'values')[0]
        fmt_json = next((f for f in self.formats_doc["formats"] if f.get("name") == name), None)
        fmt = self._normalize_one(fmt_json)
        if len(bin_s) != fmt["bit_length"]:
            messagebox.showwarning("Self-test", f"Input is {len(bin_s)} bits, format requires {fmt['bit_length']}.")
        fields = extract_fields(bin_s, fmt)
        pv = verify_parity(bin_s, fmt)
        out = [f"Format: {name}", f"Bits: {len(bin_s)}", ""]
        for k, meta in fields.items():
            s,e = meta["range"]
            out.append(f"{k:14}  {s:>3}–{e:<3}  {meta['int']:>12}  {meta['hex']:>10}")
        if pv:
            out.append("")
            for r in pv:
                s,e = r["coverage"]
                stat = "OK" if r["ok"] else ("FAIL" if r["ok"] is False else "(no parity bit)")
                out.append(f"Parity {r['type']:4}  {s:>3}–{e:<3}  expected={r['expected']} actual={r['actual']} {stat}")
        w = self._manage_widgets.get("test_out")
        if w:
            w.configure(state=tk.NORMAL)
            w.delete("1.0", tk.END)
            w.insert(tk.END, "\n".join(out))
            w.configure(state=tk.DISABLED)

    # ---------------- Calculate / Render ----------------
    def on_calculate(self):
        input_data = self.input_entry.get()
        binary_string, error = process_input(input_data)
        if error:
            messagebox.showerror("Error", error)
            return
        self.last_binary_used = binary_string
        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n")

        exact, compatible = self._detect_formats(binary_string)
        if not exact and not compatible:
            self.txt.insert(tk.END, "No matching formats found.\n")
            return

        self.last_rows_for_csv = []
        rendered_any = False
        self.tree.delete(*self.tree.get_children(''))
        self.last_format_checks = []

        if exact:
            self.txt.insert(tk.END, "== Exact bit-length matches ==\n")
            for name, fmt in exact:
                if not self.show_fails.get() and not self._parity_all_ok(binary_string, fmt):
                    continue
                self._render_format(binary_string, name, fmt)
                rendered_any = True

        if compatible:
            self.txt.insert(tk.END, "== Compatible (input longer than known format) ==\n")
            self.txt.insert(tk.END, "These may indicate framing/padding.\n\n")
            for name, fmt in compatible:
                L = fmt["bit_length"]
                use_bits = binary_string[:L] if self.slice_mode.get()=="left" else binary_string[-L:]
                if not self.show_fails.get() and not self._parity_all_ok(use_bits, fmt):
                    continue
                suffix = " (leftmost)" if self.slice_mode.get()=="left" else " (rightmost)"
                self._render_format(use_bits, name+suffix, fmt)
                rendered_any = True

        if not rendered_any:
            self.txt.insert(tk.END,
                "No formats passed parity in strict mode.\n"
                "Tip: Enable 'Show parity failures (diagnostic)' to inspect candidates.\n")

        self._draw_parity_visualizer()

    def _render_format(self, binary_string: str, name: str, fmt: dict):
        self.txt.insert(tk.END, f"Format: {name}\n")
        fields = extract_fields(binary_string, fmt)
        for field, meta in fields.items():
            self.txt.insert(tk.END,
                f"  {field:14}: {meta['int']} (hex {meta['hex']}), bits[{meta['len']}]={meta['bits']}\n")
            s,e = meta["range"]
            self.tree.insert('', tk.END, values=(field, f"{s}–{e}", meta['int'], meta['hex']))
            self.last_rows_for_csv.append({
                "Format": name, "Field": field, "Value": meta['int'], "Hex": meta['hex'],
                "BitLength": meta['len'], "Bits": meta['bits'],
            })
        pv = verify_parity(binary_string, fmt)
        if pv:
            for r in pv:
                status = "OK" if r["ok"] else ("FAIL" if r["ok"] is False else "(no parity bit)")
                self.txt.insert(tk.END,
                    f"  Parity {r['type']:4} {r['coverage'][0]}–{r['coverage'][1]}: {status} "
                    f"(expected {r['expected']}, actual {r['actual']}; data_len={r['data_len']})\n")
            self.last_format_checks = pv
        self.txt.insert(tk.END, "\n")

    def _detect_formats(self, binary_string: str):
        exact = []
        compatible = []
        n = len(binary_string)
        for name, fmt in self.FORMATS.items():
            L = fmt["bit_length"]
            if n == L:
                exact.append((name, fmt))
            elif n > L:
                compatible.append((name, fmt))
        return exact, compatible

    def _parity_all_ok(self, binary_string: str, fmt: dict) -> bool:
        pv = verify_parity(binary_string, fmt)
        if not pv:
            return True
        return all(r.get("ok", True) for r in pv)

    # ---------------- Visualizer ----------------
    def _draw_parity_visualizer(self):
        self.canvas.delete("all")
        if not self.last_binary_used:
            return
        W = self.canvas.winfo_width() or self.canvas.winfo_reqwidth()
        H = self.canvas.winfo_height() or 60
        n = len(self.last_binary_used)
        y = H//2
        self.canvas.create_line(10, y, W-10, y, fill="#4b6cff", width=4)
        for r in self.last_format_checks:
            typ = r["type"]
            s,e = r["coverage"]
            x1 = 10 + (W-20) * (s / n)
            x2 = 10 + (W-20) * (e / n)
            color = "#00adff" if typ=="even" else "#75e600"
            self.canvas.create_rectangle(x1, y-10, x2, y+10, fill=color, outline="")
            if r["ok"] is False:
                self.canvas.create_rectangle(x1, y-10, x2, y+10, fill="#ff4d4f", outline="", stipple="gray25")

    # ---------------- Copy / Export ----------------
    def copy_results(self):
        text = self.txt.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Results copied to clipboard.")

    def copy_selected_table(self):
        sel = self.tree.focus()
        if not sel:
            return
        vals = self.tree.item(sel, 'values')
        copy_text = "\t".join(str(v) for v in vals)
        self.root.clipboard_clear()
        self.root.clipboard_append(copy_text)
        messagebox.showinfo("Copied", "Selected row copied.")

    def export_csv(self):
        if not self.last_rows_for_csv:
            messagebox.showwarning("No data", "Please calculate first.")
            return
        default_name = f"hid_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name,
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Format","Field","Value","Hex","BitLength","Bits"])
            writer.writeheader()
            writer.writerows(self.last_rows_for_csv)
        messagebox.showinfo("Exported", f"Saved to {path}")

    # ---------------- Normalization ----------------
    def _normalize_formats(self, doc: dict) -> dict:
        out = {}
        for f in doc.get("formats", []):
            name = f.get("name","Format")
            bitlen = int(f.get("bit_length", 0))
            fields = {fld["name"]: (int(fld["start"]), int(fld["end"])) for fld in f.get("fields", [])}
            parity_cov = []
            for p in f.get("parity", []):
                typ = p.get("type","even").lower()
                ranges = [(int(r["start"]), int(r["end"])) for r in p.get("ranges", [])]
                if ranges:
                    parity_cov.append({"type": typ, "ranges": ranges})
            out[name] = {"bit_length": bitlen, "fields": fields, "parity_coverage": parity_cov}
        return out

    def _normalize_one(self, f: dict) -> dict:
        return self._normalize_formats({"formats":[f]} )[f.get("name")]

# ---------------- Main ----------------
def ensure_bootstrap_configs():
    try:
        appdata = appdata_dir()
        os.makedirs(appdata, exist_ok=True)
        tpath = config_path("theme.json")
        fpath = config_path("formats.json")
        if not os.path.exists(tpath):
            with open(tpath, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_THEME, f, indent=2)
        if not os.path.exists(fpath):
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_FORMATS, f, indent=2)
    except Exception:
        try:
            with open("theme.json", "w", encoding="utf-8") as f:
                json.dump(DEFAULT_THEME, f, indent=2)
            with open("formats.json", "w", encoding="utf-8") as f:
                json.dump(DEFAULT_FORMATS, f, indent=2)
        except Exception:
            pass

def main():
    log_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "BinarySlicer")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = "."
    log_file = os.path.join(log_dir, "logs.txt")

    try:
        ensure_bootstrap_configs()
        root = tk.Tk()

        # --- Set window icon (works for script & PyInstaller) ---
        try:
            # Where to look for assets:
            # - normal run: folder of this script
            # - PyInstaller: temporary _MEIPASS
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

            ico_path = os.path.join(base_dir, "icons", "jci_globe.ico")
            if os.path.exists(ico_path):
                root.iconbitmap(ico_path)   # best on Windows
            else:
                # PNG fallback (title bar/taskbar on some setups)
                png_path = os.path.join(base_dir, "icons", "jci_globe_256.png")
                if os.path.exists(png_path):
                    icon = tk.PhotoImage(file=png_path)
                    root.iconphoto(True, icon)
        except Exception as e:
            print(f"Could not set window icon: {e}")

        app = App(root)
        root.minsize(900, 560)
        root.mainloop()

        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}]\n{tb}\n")
        except Exception:
            pass
        try:
            messagebox.showerror(
                "BinarySlicer crashed",
                f"An error occurred and was logged to:\n{log_file}\n\n{e}"
            )
        except Exception:
            print("BinarySlicer crashed:\n", tb)
        sys.exit(1)

if __name__ == "__main__":
    main()
