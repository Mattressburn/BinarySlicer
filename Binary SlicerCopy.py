#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HID Binary/Hex Calculator (Diagnostic Mode + Rightmost Slicing Option)
- Accepts Hex (with/without 0x, spaces, hyphens) or Binary input
- Prefers exact bit-length matches; also shows "compatible" (longer) inputs separately
- Extracts fields for common HID/Wiegand formats (26, 34, 37 variants, 40, 48)
- Verifies parity for H10301 (26-bit) and H10306 (34-bit)
- UI: Copy Results, Export CSV, a checkbox to show parity failures (diagnostic),
      and a Leftmost/Rightmost slicing option for compatible matches.

Note: Some 40/48-bit layouts are placeholders—verify against your controller/vendor docs,
especially for Corporate 1000 (customer-specific field assignments).
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import csv
from datetime import datetime
import textwrap  # used for readable binary grouping

# Define HID card formats with bit length and field definitions
# Field index ranges are [start, end) zero-based bit positions, counting from MSB at index 0.
HID_FORMATS = {
    "H10301 (26-bit)": {
        "bit_length": 26,
        "fields": {
            "Even Parity": (0, 1),      # parity bit only
            "Site Code":   (1, 9),
            "Card Number": (9, 25),
            "Odd Parity":  (25, 26),    # parity bit only
        },
        # Parity coverage: ranges of DATA bits that each parity bit protects
        "parity_coverage": {
            "even": (1, 13),  # bits 1-12 inclusive -> [1,13)
            "odd":  (13, 25), # bits 13-24 inclusive -> [13,25)
        }
    },
    "H10306 (34-bit)": {
        "bit_length": 34,
        "fields": {
            "Even Parity": (0, 1),
            "Site Code":   (1, 17),
            "Card Number": (17, 33),
            "Odd Parity":  (33, 34),
        },
        "parity_coverage": {
            "even": (1, 17),  # bits 1-16
            "odd":  (17, 33), # bits 17-32
        }
    },
    "H10302 (37-bit)": {
        "bit_length": 37,
        "fields": {
            "Even Parity": (0, 1),
            # No site code in H10302 open 37-bit
            "Card Number": (1, 36),
            "Odd Parity":  (36, 37),
        },
        # Parity rules vary by implementation; left unspecified here.
    },
    "H10304 (37-bit with Site Code)": {
        "bit_length": 37,
        "fields": {
            "Even Parity": (0, 1),
            "Site Code":   (1, 16),
            "Card Number": (16, 36),
            "Odd Parity":  (36, 37),
        },
        # Parity rules vary by implementation; add coverage once confirmed.
    },
    "H2004064 (48-bit Corporate 1000)": {
        "bit_length": 48,
        # NOTE: Corporate 1000 is customer-specific; below is a common mapping used in some controllers.
        "fields": {
            "Even Parity":     (0, 1),
            "Company ID Code": (1, 23),   # 22 bits
            "Card ID Number":  (23, 46),  # 23 bits
            "Odd Parity":      (46, 47),  # parity near end (some systems may differ)
            # Bit 47..48 occasionally used for stop/sentinel; confirm per deployment.
        },
        # No generic parity coverage provided here (varies).
    },
    "P10001 (40-bit Honeywell)": {
        "bit_length": 40,
        "fields": {
            "Site Code":   (0, 12),
            "Card Number": (12, 36),
            "XOR Byte":    (36, 38),
            "One":         (38, 40),
        },
    },
    "CASI-RUSCO (40-bit)": {
        "bit_length": 40,
        "fields": {
            # Placeholder — actual layouts vary; treat as opaque 40-bit identifier when unknown.
            "Card Number": (0, 40),
        },
    },
    "XCEEDID RS2 (40-bit)": {
        "bit_length": 40,
        "fields": {
            # Placeholder; verify against controller docs for production.
            "Even Parity": (0, 1),
            "Site Code":   (1, 11),
            "Card Number": (11, 39),
            "Odd Parity":  (39, 40),
        },
    },
}

HEX_CHARS = set("0123456789abcdefABCDEF")


def clean_input(s: str) -> str:
    return s.strip()


def is_binary(s: str) -> bool:
    return all(ch in '01' for ch in s) and len(s) > 0


def is_hex(s: str) -> bool:
    return all(ch in HEX_CHARS for ch in s) and len(s) > 0


def hex_to_binary(hex_string: str) -> str:
    try:
        return bin(int(hex_string, 16))[2:].zfill(len(hex_string) * 4)
    except ValueError:
        return None


def process_input(input_string: str):
    # Normalize: remove spaces, hyphens, underscores; allow optional 0x prefix
    s = clean_input(input_string)
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    if s.startswith(('0x', '0X')):
        s = s[2:]
    # Try binary first
    if is_binary(s):
        return s, None
    # Try hex
    if is_hex(s):
        b = hex_to_binary(s)
        if b is None:
            return None, "Invalid hex input."
        return b, None
    return None, "Input must be hex or binary (e.g., 0x1A2B, 1100101)."


def detect_formats(binary_string: str):
    exact = []
    compatible = []  # longer payload containing a known length
    n = len(binary_string)
    for name, fmt in HID_FORMATS.items():
        L = fmt["bit_length"]
        if n == L:
            exact.append((name, fmt))
        elif n > L:
            compatible.append((name, fmt))
    return exact, compatible


def extract_bits(binary_string: str, start: int, end: int) -> str:
    return binary_string[start:end]


def bits_to_int(bits: str) -> int:
    return int(bits, 2) if bits else 0


def extract_fields(binary_string: str, fmt: dict):
    fields = {}
    for field, (start, end) in fmt["fields"].items():
        bits = extract_bits(binary_string, start, end)
        fields[field] = {
            "bits": bits,
            "int": bits_to_int(bits),
            "hex": f"0x{bits_to_int(bits):X}",
            "len": end - start,
        }
    return fields


def parity_even(bits: str) -> int:
    """Return the parity bit that makes total number of 1s even."""
    ones = bits.count('1')
    return 0 if ones % 2 == 0 else 1


def parity_odd(bits: str) -> int:
    """Return the parity bit that makes total number of 1s odd."""
    ones = bits.count('1')
    return 1 if ones % 2 == 0 else 0


def verify_parity(binary_string: str, fmt_name: str, fmt: dict):
    """Compute expected vs actual parity for formats that define coverage."""
    result = {}
    coverage = fmt.get("parity_coverage")
    if not coverage:
        return result  # no rules defined
    fields = fmt["fields"]
    # Even parity check
    if "Even Parity" in fields and "even" in coverage:
        p_bit = bits_to_int(extract_bits(binary_string, *fields["Even Parity"]))
        data_bits = extract_bits(binary_string, *coverage["even"])
        expected = parity_even(data_bits)
        result["Even Parity"] = {
            "expected": expected,
            "actual": p_bit,
            "ok": expected == p_bit,
            "data_len": len(data_bits),
        }
    # Odd parity check
    if "Odd Parity" in fields and "odd" in coverage:
        p_bit = bits_to_int(extract_bits(binary_string, *fields["Odd Parity"]))
        data_bits = extract_bits(binary_string, *coverage["odd"])
        expected = parity_odd(data_bits)
        result["Odd Parity"] = {
            "expected": expected,
            "actual": p_bit,
            "ok": expected == p_bit,
            "data_len": len(data_bits),
        }
    return result


def parity_all_ok(binary_string: str, fmt: dict) -> bool:
    """True if no parity rules are defined OR all defined parity checks pass."""
    pv = verify_parity(binary_string, "", fmt)
    return (not pv) or all(entry.get("ok", True) for entry in pv.values())


def format_binary_groups(b: str, group: int = 4) -> str:
    """Group binary string from MSB in blocks for readability (e.g., 1111 0000 1010)."""
    if group <= 0:
        return b
    rem = len(b) % group
    leading = '' if rem == 0 else b[:rem] + ' '
    rest = b[rem:]
    return leading + ' '.join(textwrap.wrap(rest, group)) if rest else b


# --------------------- GUI ---------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("HID Binary Calculator (v2 + Diagnostic Mode + Rightmost Slicing)")

        frame = ttk.Frame(root, padding=10)
        frame.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        ttk.Label(frame, text="Enter Hex or Binary:").grid(row=0, column=0, sticky=tk.W)
        self.input_entry = ttk.Entry(frame, width=64)
        self.input_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))
        frame.columnconfigure(1, weight=1)

        self.calc_btn = ttk.Button(frame, text="Calculate", command=self.on_calculate)
        self.calc_btn.grid(row=0, column=2, padx=6)

        self.copy_btn = ttk.Button(frame, text="Copy Results", command=self.copy_results)
        self.copy_btn.grid(row=0, column=3, padx=6)

        self.export_btn = ttk.Button(frame, text="Export CSV", command=self.export_csv)
        self.export_btn.grid(row=0, column=4, padx=6)

        # Diagnostic toggle: show parity failures
        self.show_fails = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text="Show parity failures (diagnostic)", variable=self.show_fails
        ).grid(row=0, column=5, padx=6)

        # Slicing mode for compatible matches: leftmost (default) or rightmost
        ttk.Label(frame, text="Compatible slicing:").grid(row=0, column=6, padx=(12, 2))
        self.slice_mode = tk.StringVar(value="left")  # 'left' or 'right'
        ttk.Radiobutton(frame, text="Leftmost", value="left", variable=self.slice_mode).grid(row=0, column=7, padx=2)
        ttk.Radiobutton(frame, text="Rightmost", value="right", variable=self.slice_mode).grid(row=0, column=8, padx=2)

        self.results = tk.Text(frame, width=100, height=26)
        self.results.grid(row=1, column=0, columnspan=9, pady=10, sticky=(tk.N, tk.S, tk.E, tk.W))
        frame.rowconfigure(1, weight=1)

        self.last_rows_for_csv = []

    def on_calculate(self):
        input_data = self.input_entry.get()
        binary_string, error = process_input(input_data)
        if error:
            messagebox.showerror("Error", error)
            return
        self.results.delete("1.0", tk.END)

        self.results.insert(tk.END, f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n")

        exact, compatible = detect_formats(binary_string)

        if not exact and not compatible:
            self.results.insert(tk.END, "No matching HID formats found.\n")
            return

        self.last_rows_for_csv = []
        rendered_any = False

        if exact:
            self.results.insert(tk.END, "== Exact bit-length matches ==\n")
            for name, fmt in exact:
                if not self.show_fails.get() and not parity_all_ok(binary_string, fmt):
                    continue
                self.render_format(binary_string, name, fmt)
                rendered_any = True

        if compatible:
            self.results.insert(tk.END, "== Compatible (input longer than known format) ==\n")
            self.results.insert(
                tk.END,
                "These may indicate your payload contains framing or facility-specific padding.\n\n"
            )
            for name, fmt in compatible:
                L = fmt["bit_length"]
                if self.slice_mode.get() == "left":
                    use_bits = binary_string[:L]
                    slice_note = " (using leftmost bits)"
                else:
                    use_bits = binary_string[-L:]
                    slice_note = " (using rightmost bits)"
                if not self.show_fails.get() and not parity_all_ok(use_bits, fmt):
                    continue
                self.render_format(use_bits, name + slice_note, fmt)
                rendered_any = True

        if not rendered_any:
            self.results.insert(
                tk.END,
                "No formats passed parity in strict mode.\n"
                "Tip: Enable 'Show parity failures (diagnostic)' to inspect candidates and troubleshoot.\n"
            )

    def render_format(self, binary_string: str, name: str, fmt: dict):
        self.results.insert(tk.END, f"Format: {name}\n")
        fields = extract_fields(binary_string, fmt)
        for field, meta in fields.items():
            self.results.insert(
                tk.END,
                f"  {field:14}: {meta['int']} (hex {meta['hex']}), bits[{meta['len']}]={meta['bits']}\n"
            )
            # Save for CSV
            self.last_rows_for_csv.append({
                "Format": name,
                "Field": field,
                "Value": meta['int'],
                "Hex": meta['hex'],
                "BitLength": meta['len'],
                "Bits": meta['bits'],
            })
        # Parity verification if available
        pv = verify_parity(binary_string, name, fmt)
        if pv:
            for k, v in pv.items():
                status = "OK" if v["ok"] else "FAIL"
                self.results.insert(
                    tk.END,
                    f"  {k:14}: {status} (expected {v['expected']}, actual {v['actual']}; data_len={v['data_len']})\n"
                )
        self.results.insert(tk.END, "\n")

    def copy_results(self):
        text = self.results.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Results copied to clipboard.")

    def export_csv(self):
        if not self.last_rows_for_csv:
            messagebox.showwarning("No data", "Please calculate first.")
            return
        # Ask for save location
        default_name = f"hid_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name,
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Format", "Field", "Value", "Hex", "BitLength", "Bits"])
            writer.writeheader()
            writer.writerows(self.last_rows_for_csv)
        messagebox.showinfo("Exported", f"Saved to {path}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()