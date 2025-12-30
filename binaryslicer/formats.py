"""Format loading, normalization, field extraction, and parity helpers.

This module is intentionally "format pack" friendly:
- It accepts the existing JSON schema used by BinarySlicer.
- It also supports optional per-field "view" decoding so that formats like
  FASC-N can be rendered the same way as the Excel sheet.

Supported field views:
- (default) binary: interpret the whole field as a binary integer
- ansi_bcd5 / ansi_bcd: interpret the field as 5-bit ANSI BCD characters:
    - bit 0 (leftmost) is the parity bit
    - bits 1..4 are the data bits, but interpreted LSB-first
      (this matches the Excel sheet which reverses the 5-bit string and takes 4 bits)
    - multi-character fields produce a digit string; "int" becomes the decimal integer
      if all characters are digits

Supported parity rules:
- ranges-based rules (existing behavior)
- per_character rules, for example:
    {"type": "odd", "per_character": true, "character_width": 5, "parity_position": "msb"}
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, MutableMapping, Optional, Sequence, Tuple

from .config import load_json, save_json
from .resources import default_formats

FORMATS_FILENAME = "formats.json"

FieldRange = Tuple[int, int]


@dataclass
class NormalizedFormat:
    name: str
    bit_length: int
    fields: Dict[str, FieldRange]
    parity_coverage: List[Dict]
    raw: Dict
    field_views: Dict[str, str] = field(default_factory=dict)
    field_hidden: Dict[str, bool] = field(default_factory=dict)


class FormatRepository:
    """Stateful access to format documents."""

    def __init__(self) -> None:
        self._doc = load_formats_document()

    @property
    def document(self) -> Dict:
        return self._doc

    @property
    def formats(self) -> Dict[str, NormalizedFormat]:
        return normalize_formats(self._doc)

    def refresh(self) -> None:
        self._doc = load_formats_document()

    def save(self) -> None:
        save_formats_document(self._doc)

    def update(self, doc: Dict) -> None:
        self._doc = doc
        save_formats_document(self._doc)

    def merge(self, incoming: Dict) -> None:
        self._doc = merge_formats(self._doc, incoming)
        save_formats_document(self._doc)


def load_formats_document() -> Dict:
    return load_json(FORMATS_FILENAME, default_formats)


def save_formats_document(doc: Dict) -> None:
    save_json(FORMATS_FILENAME, doc)


def merge_formats(base: Dict, incoming: Dict) -> Dict:
    merged = copy.deepcopy(base)
    existing = {fmt.get("name"): i for i, fmt in enumerate(merged.get("formats", []))}
    for fmt in incoming.get("formats", []):
        name = fmt.get("name")
        if not name:
            continue
        if name in existing:
            merged["formats"][existing[name]] = fmt
        else:
            merged.setdefault("formats", []).append(fmt)
    return merged


def _coerce_range(entry: MutableMapping) -> FieldRange:
    return int(entry.get("start", 0)), int(entry.get("end", 0))


def _normalize_parity_to_list(parity) -> List[Dict]:
    """Accept list or dict parity definitions and normalize to a list."""
    if not parity:
        return []
    if isinstance(parity, list):
        return [p for p in parity if isinstance(p, dict)]
    if isinstance(parity, dict):
        # Two supported dict shapes:
        # 1) {"even": [...], "odd": [...]}
        # 2) {"type": "...", "per_character": true, ...} or {"type": "...", "ranges": [...]}
        if "type" in parity or "per_character" in parity or "ranges" in parity:
            return [parity]
        rules: List[Dict] = []
        for typ in ("even", "odd"):
            ranges = parity.get(typ)
            if not ranges:
                continue
            normalized = [ranges] if isinstance(ranges, dict) else list(ranges)
            rules.append({"type": typ, "ranges": normalized})
        return rules
    return []


def normalize_format_entry(entry: Dict) -> NormalizedFormat:
    name = entry.get("name", "Format")
    bitlen = int(entry.get("bit_length", 0))

    fields: Dict[str, FieldRange] = {}
    views: Dict[str, str] = {}
    hidden: Dict[str, bool] = {}

    for fld in entry.get("fields", []) or []:
        if not isinstance(fld, dict):
            continue
        fname = fld.get("name", "Field")
        fields[fname] = _coerce_range(fld)
        view = fld.get("view") or fld.get("decode")  # allow either key
        if isinstance(view, str) and view.strip():
            views[fname] = view.strip().lower()
        if bool(fld.get("hidden")):
            hidden[fname] = True

    parity_cov: List[Dict] = []
    for rule in _normalize_parity_to_list(entry.get("parity")):
        typ = str(rule.get("type", "even")).lower()

        # per-character parity rule (common for 5-bit ANSI BCD)
        if bool(rule.get("per_character")):
            parity_cov.append(
                {
                    "type": typ,
                    "per_character": True,
                    "character_width": int(rule.get("character_width", 5)),
                    "parity_position": str(rule.get("parity_position", "msb")).lower(),
                    "start": int(rule.get("start", 0)),
                    "end": int(rule.get("end", bitlen - 1 if bitlen else 0)),
                    "gate": bool(rule.get("gate", False)),
                }
            )
            continue

        ranges = [_coerce_range(r) for r in (rule.get("ranges", []) or []) if isinstance(r, dict)]
        if ranges:
            parity_cov.append({"type": typ, "ranges": ranges, "gate": bool(rule.get("gate", True))})

    return NormalizedFormat(
        name=name,
        bit_length=bitlen,
        fields=fields,
        parity_coverage=parity_cov,
        raw=entry,
        field_views=views,
        field_hidden=hidden,
    )


def normalize_formats(doc: Dict) -> Dict[str, NormalizedFormat]:
    result: Dict[str, NormalizedFormat] = {}
    for entry in doc.get("formats", []) or []:
        if not isinstance(entry, dict):
            continue
        fmt = normalize_format_entry(entry)
        result[fmt.name] = fmt
    return result


def extract_bits(binary_string: str, start: int, end: int) -> str:
    return binary_string[start : end + 1]


def bits_to_int(bits: str) -> int:
    return int(bits, 2) if bits else 0


# ---------------- ANSI BCD 5-bit decoding (Excel-compatible) ----------------

_SENTINEL_MAP = {
    "11010": "SS",  # Start Sentinel (commonly 0x1A)
    "10110": "FS",  # Field Separator (commonly 0x16)
    "11111": "ES",  # End Sentinel (commonly 0x1F)
}


def _ansi_bcd5_digit_from_chunk(
    chunk5: str,
    parity_position: str = "msb",
    allow_extended: bool = False,
    coerce_invalid: bool = False,
) -> Optional[str]:
    """Decode a single 5-bit ANSI BCD chunk to a digit.

    Excel logic (as seen in the provided sheet) effectively:
    - reverses the 5-bit string
    - takes the first 4 bits
    - BIN2DEC of that
    That means:
      chunk = p d1 d2 d3 d4  (p is parity bit, leftmost)
      reverse(chunk) = d4 d3 d2 d1 p
      take left4 => d4 d3 d2 d1  (LSB-first data interpreted as MSB-first)
    """
    if len(chunk5) != 5 or any(ch not in "01" for ch in chunk5):
        return None

    # Allow sentinel tokens to pass through as non-digits.
    if chunk5 in _SENTINEL_MAP:
        return None

    if parity_position == "lsb":
        data = chunk5[:-1]     # d1 d2 d3 d4 (parity on the right)
    else:
        data = chunk5[1:]      # d1 d2 d3 d4 (parity on the left)
    data_rev = data[::-1]      # d4 d3 d2 d1
    val = int(data_rev, 2)
    if 0 <= val <= 9:
        return str(val)
    if allow_extended:
        return f"{val:X}"
    if coerce_invalid:
        return "0"
    return None


def decode_ansi_bcd5_field(bits: str, view: str | None = None) -> Dict[str, object]:
    """Decode a field that is made up of 5-bit ANSI BCD characters."""
    out: Dict[str, object] = {
        "display": "",
        "int": 0,
        "hex": "",
        "ok_digits": False,
    }

    parity_position = "lsb" if view and "lsb" in view else "msb"
    allow_extended = bool(view and "hex" in view)
    coerce_invalid = bool(view and ("coerce" in view or "digit" in view))

    if not bits or len(bits) % 5 != 0:
        # Not aligned, fall back to binary integer interpretation
        val = bits_to_int(bits)
        out["display"] = str(val)
        out["int"] = val
        out["hex"] = f"0x{val:X}"
        out["ok_digits"] = False
        return out

    chunks = [bits[i : i + 5] for i in range(0, len(bits), 5)]
    digits: List[str] = []
    tokens: List[str] = []

    for ch in chunks:
        d = _ansi_bcd5_digit_from_chunk(
            ch,
            parity_position=parity_position,
            allow_extended=allow_extended,
            coerce_invalid=coerce_invalid,
        )
        if d is not None:
            digits.append(d)
            tokens.append(d)
        else:
            # preserve known sentinel/separator labels if present
            tokens.append(_SENTINEL_MAP.get(ch, f"0b{ch}"))

    display = "".join(tokens)
    out["display"] = display

    if all(t.isdigit() for t in tokens) and tokens:
        num = int("".join(tokens))
        out["int"] = num
        out["hex"] = f"0x{num:X}"
        out["ok_digits"] = True
    else:
        # If mixed, keep a sensible numeric fallback as the raw binary int.
        val = bits_to_int(bits)
        out["int"] = val
        out["hex"] = f"0x{val:X}"
        out["ok_digits"] = False

    return out


def extract_fields(binary_string: str, fmt: NormalizedFormat) -> Dict[str, Dict]:
    fields: Dict[str, Dict] = {}
    for field_name, (start, end) in fmt.fields.items():
        bits = extract_bits(binary_string, start, end)
        view = (fmt.field_views.get(field_name) or "").lower().strip()
        hidden = fmt.field_hidden.get(field_name, False)

        if view in ("ansi_bcd5", "ansi_bcd") or view.startswith("ansi_bcd5"):
            decoded = decode_ansi_bcd5_field(bits, view=view)
            value = int(decoded["int"])
            hexval = str(decoded["hex"])
            display = str(decoded["display"])
        else:
            value = bits_to_int(bits)
            hexval = f"0x{value:X}"
            display = str(value)

        fields[field_name] = {
            "bits": bits,
            "int": value,
            "hex": hexval,
            "display": display,  # UI can choose to show this instead of "int"
            "len": end - start + 1,
            "range": (start, end),
            "view": view or "binary",
            "hidden": hidden,
        }
    return fields


# ---------------- Parity helpers ----------------

def _parse_parity_range(r) -> Optional[FieldRange]:
    if isinstance(r, dict) and "start" in r and "end" in r:
        return int(r["start"]), int(r["end"])
    if isinstance(r, (list, tuple)) and len(r) >= 2:
        return int(r[0]), int(r[1])
    return None


def parity_even_bit_needed(bits: str) -> int:
    return 0 if bits.count("1") % 2 == 0 else 1


def parity_odd_bit_needed(bits: str) -> int:
    return 1 if bits.count("1") % 2 == 0 else 0


def _collect_parity_bit_positions(fmt: NormalizedFormat) -> List[int]:
    positions: List[int] = []
    for fld in fmt.raw.get("fields", []) or []:
        if not isinstance(fld, dict):
            continue
        if str(fld.get("role", "")).lower() != "parity":
            continue
        try:
            s = int(fld.get("start", fld.get("end", 0)))
            e = int(fld.get("end", s))
        except (TypeError, ValueError):
            continue
        positions.extend([s, e])
    return sorted(set(positions))


def _guess_parity_bit_index(fmt: NormalizedFormat, start: int, end: int, total_bits: int) -> Optional[int]:
    candidates = _collect_parity_bit_positions(fmt)
    adjacent = {start - 1, end + 1}
    for cand in candidates:
        if cand in adjacent:
            return cand
    if candidates:
        return min(candidates, key=lambda c: min(abs(c - start), abs(c - end)))
    for cand in sorted(adjacent):
        if 0 <= cand < total_bits:
            return cand
    return None


def _build_parity_entry(
    binary_string: str, typ: str, start: int, end: int, parity_bit_index: int | None, gate: bool = True
) -> Dict:
    data_bits = extract_bits(binary_string, start, end)
    expected = parity_even_bit_needed(data_bits) if typ == "even" else parity_odd_bit_needed(data_bits)
    actual: Optional[int] = None
    if parity_bit_index is not None and 0 <= parity_bit_index < len(binary_string):
        actual = int(binary_string[parity_bit_index])
    ok: Optional[bool] = None if actual is None else actual == expected
    return {
        "label": "Even Parity" if typ == "even" else "Odd Parity",
        "type": typ,
        "coverage": (start, end),
        "expected": expected,
        "actual": actual,
        "ok": ok,
        "parity_bit": parity_bit_index,
        "gate": gate,
        "data_len": len(data_bits),
    }


def _build_per_character_parity_entries(
    binary_string: str,
    typ: str,
    start: int,
    end: int,
    character_width: int,
    parity_position: str,
    gate: bool,
) -> List[Dict]:
    """Generate parity checks for each fixed-width character."""
    result: List[Dict] = []
    if character_width <= 1:
        return result

    # Clamp and align
    start = max(0, start)
    end = min(len(binary_string) - 1, end)
    if end < start:
        return result

    segment = binary_string[start : end + 1]
    n = len(segment) // character_width

    for i in range(n):
        c_start = start + i * character_width
        c_end = c_start + character_width - 1
        chunk = extract_bits(binary_string, c_start, c_end)

        if len(chunk) != character_width:
            continue

        if parity_position == "lsb":
            parity_bit = chunk[-1]
            data_bits = chunk[:-1]
        else:
            # default msb
            parity_bit = chunk[0]
            data_bits = chunk[1:]

        expected = parity_even_bit_needed(data_bits) if typ == "even" else parity_odd_bit_needed(data_bits)
        actual = int(parity_bit)
        ok = (actual == expected)

        result.append(
            {
                "label": "Even Parity (char)" if typ == "even" else "Odd Parity (char)",
                "type": typ,
                "coverage": (c_start, c_end),
                "expected": expected,
                "actual": actual,
                "ok": ok,
                "gate": gate,
                "data_len": len(data_bits),
            }
        )

    return result


def verify_parity(binary_string: str, fmt: NormalizedFormat) -> List[Dict]:
    coverage = fmt.parity_coverage or fmt.raw.get("parity")
    rules = _normalize_parity_to_list(coverage)
    if not rules:
        return []

    result: List[Dict] = []
    for rule in rules:
        typ = str(rule.get("type", "even")).lower()

        if bool(rule.get("per_character")):
            character_width = int(rule.get("character_width", 5))
            parity_position = str(rule.get("parity_position", "msb")).lower()
            start = int(rule.get("start", 0))
            end = int(rule.get("end", len(binary_string) - 1))
            gate = bool(rule.get("gate", True))
            result.extend(
                _build_per_character_parity_entries(
                    binary_string=binary_string,
                    typ=typ,
                    start=start,
                    end=end,
                    character_width=character_width,
                    parity_position=parity_position,
                    gate=gate,
                )
            )
            continue

        for rng in rule.get("ranges", []) or []:
            parsed = _parse_parity_range(rng)
            if not parsed:
                continue
            start, end = parsed
            parity_bit_index = _guess_parity_bit_index(fmt, start, end, len(binary_string))
            result.append(_build_parity_entry(binary_string, typ, start, end, parity_bit_index, gate=bool(rule.get("gate", True))))

    return result


__all__ = [
    "FORMATS_FILENAME",
    "FormatRepository",
    "NormalizedFormat",
    "bits_to_int",
    "extract_bits",
    "extract_fields",
    "merge_formats",
    "normalize_format_entry",
    "normalize_formats",
    "parity_even_bit_needed",
    "parity_odd_bit_needed",
    "verify_parity",
    "load_formats_document",
    "save_formats_document",
    "decode_ansi_bcd5_field",
]
