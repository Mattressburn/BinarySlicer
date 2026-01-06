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
import itertools
import json
from dataclasses import dataclass, field
from typing import Dict, List, MutableMapping, Optional, Sequence, Tuple

from .config import ConfigError, _parse_version, _read_json, save_json
from .paths import ensure_user_config_dir, user_config_dir
from .resources import default_formats

FORMATS_FILENAME = "formats.json"

FieldRange = Tuple[int, int]


class FormatValidationError(ValueError):
    """Raised when a format entry fails validation."""


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
        self.last_errors: List[str] = []
        self._formats = normalize_formats(self._doc, self.last_errors)

    @property
    def document(self) -> Dict:
        return self._doc

    @property
    def formats(self) -> Dict[str, NormalizedFormat]:
        return self._formats

    def refresh(self) -> None:
        self._doc = load_formats_document()
        self.last_errors = []
        self._formats = normalize_formats(self._doc, self.last_errors)

    def save(self) -> None:
        save_formats_document(self._doc)

    def update(self, doc: Dict) -> None:
        self._doc = doc
        self.last_errors = []
        self._formats = normalize_formats(self._doc, self.last_errors)
        save_formats_document(self._doc)

    def merge(self, incoming: Dict) -> None:
        self._doc = merge_formats(self._doc, incoming)
        self.last_errors = []
        self._formats = normalize_formats(self._doc, self.last_errors)
        save_formats_document(self._doc)


def _version_tuple(value: object) -> Tuple[int, ...]:
    if isinstance(value, str):
        return _parse_version(value.replace("-", ".").split("."))
    if isinstance(value, (list, tuple)):
        return _parse_version(value)
    return _parse_version([value])


def _format_pack_is_newer(bundled: Dict, user: Dict) -> bool:
    return _version_tuple(bundled.get("format_pack_version", 0)) > _version_tuple(
        user.get("format_pack_version", 0)
    )


def load_formats_document() -> Dict:
    """Load the formats document, upgrading the user copy when the bundle is newer."""

    ensure_user_config_dir()
    bundled_doc = default_formats()
    user_path = user_config_dir() / FORMATS_FILENAME

    try:
        user_doc = _read_json(user_path)
    except FileNotFoundError:
        user_doc = None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {user_path}") from exc

    if user_doc is None:
        save_formats_document(bundled_doc)
        return bundled_doc

    if bundled_doc and _format_pack_is_newer(bundled_doc, user_doc):
        save_formats_document(bundled_doc)
        return bundled_doc

    return user_doc


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
                    "allow_mixed_parity": bool(rule.get("allow_mixed_parity", False)),
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


def validate_format_entry(entry: Dict, normalized: Optional[NormalizedFormat] = None) -> None:
    """Validate a format entry and raise FormatValidationError on problems."""

    fmt_name = entry.get("name", "Format")
    bitlen_raw = entry.get("bit_length")
    if not isinstance(bitlen_raw, int):
        raise FormatValidationError(f"Format '{fmt_name}' is missing a valid integer bit_length.")
    if bitlen_raw <= 0:
        raise FormatValidationError(f"Format '{fmt_name}' must have bit_length > 0 (got {bitlen_raw}).")
    bitlen = bitlen_raw

    def _validate_range(label: str, start: int, end: int) -> None:
        if start < 0 or end < 0:
            raise FormatValidationError(
                f"Format '{fmt_name}' has negative range for {label}: start={start}, end={end}."
            )
        if end < start:
            raise FormatValidationError(
                f"Format '{fmt_name}' has end < start for {label}: start={start}, end={end}."
            )
        if end >= bitlen:
            raise FormatValidationError(
                f"Format '{fmt_name}' range exceeds bit_length for {label}: end={end}, bit_length={bitlen}."
            )

    fields = entry.get("fields", []) or []
    for fld in fields:
        if not isinstance(fld, dict):
            raise FormatValidationError(f"Format '{fmt_name}' has a non-dict field entry.")
        try:
            start = int(fld.get("start", 0))
            end = int(fld.get("end", 0))
        except (TypeError, ValueError):
            raise FormatValidationError(f"Format '{fmt_name}' field '{fld.get('name','Field')}' has invalid bounds.")
        _validate_range(f"field '{fld.get('name','Field')}'", start, end)

    # Parity validation (ranges or per_character)
    coverage: List[Dict] = []
    if normalized is not None:
        coverage = normalized.parity_coverage
    else:
        coverage = _normalize_parity_to_list(entry.get("parity"))
    for rule in coverage:
        if bool(rule.get("per_character")):
            try:
                start = int(rule.get("start", 0))
                end = int(rule.get("end", bitlen - 1))
            except (TypeError, ValueError):
                raise FormatValidationError(f"Format '{fmt_name}' has malformed per-character parity range.")
            _validate_range("parity range", start, end)
        for rng in rule.get("ranges", []) or []:
            try:
                parsed = _parse_parity_range(rng)
            except Exception as exc:  # noqa: BLE001
                raise FormatValidationError(f"Format '{fmt_name}' has malformed parity range.") from exc
            if not parsed:
                raise FormatValidationError(f"Format '{fmt_name}' has malformed parity range.")
            _validate_range("parity range", parsed[0], parsed[1])

    # Overlap detection (non-hidden fields)
    hidden_map: Dict[str, bool] = {}
    field_ranges: Dict[str, FieldRange] = {}
    if normalized is not None:
        hidden_map = normalized.field_hidden
        field_ranges = normalized.fields
    else:
        for fld in fields:
            if not isinstance(fld, dict):
                continue
            name = fld.get("name", "Field")
            hidden_map[name] = bool(fld.get("hidden"))
            try:
                field_ranges[name] = (int(fld.get("start", 0)), int(fld.get("end", 0)))
            except (TypeError, ValueError):
                continue
    for (n1, r1), (n2, r2) in itertools.combinations(field_ranges.items(), 2):
        if hidden_map.get(n1) or hidden_map.get(n2):
            continue
        if max(r1[0], r2[0]) <= min(r1[1], r2[1]):
            raise FormatValidationError(f"Format '{fmt_name}' has overlapping fields: {n1} and {n2}.")


def normalize_formats(doc: Dict, errors: Optional[List[str]] = None) -> Dict[str, NormalizedFormat]:
    """Normalize and validate a formats document.

    Invalid formats are skipped when errors is provided; otherwise a
    FormatValidationError is raised.
    """
    result: Dict[str, NormalizedFormat] = {}
    for entry in doc.get("formats", []) or []:
        if not isinstance(entry, dict):
            continue
        try:
            fmt = normalize_format_entry(entry)
            validate_format_entry(entry, fmt)
        except FormatValidationError as exc:
            if errors is not None:
                errors.append(str(exc))
                continue
            raise
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
    allow_mixed_parity: bool = False,
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
            parity_index = c_end
        else:
            # default msb
            parity_bit = chunk[0]
            data_bits = chunk[1:]
            parity_index = c_start

        typ_used = typ
        expected = parity_even_bit_needed(data_bits) if typ == "even" else parity_odd_bit_needed(data_bits)
        actual = int(parity_bit)
        ok = (actual == expected)
        used_alternate = False
        if allow_mixed_parity and not ok:
            alt_type = "odd" if typ == "even" else "even"
            alt_expected = parity_even_bit_needed(data_bits) if alt_type == "even" else parity_odd_bit_needed(data_bits)
            if actual == alt_expected:
                ok = True
                expected = alt_expected
                typ_used = alt_type
                used_alternate = True

        label_base = "Even Parity (char)" if typ_used == "even" else "Odd Parity (char)"
        label = f"{label_base} [alt]" if used_alternate else label_base

        result.append(
            {
                "label": label,
                "type": typ_used,
                "configured_type": typ,
                "coverage": (c_start, c_end),
                "expected": expected,
                "actual": actual,
                "ok": ok,
                "parity_bit": parity_index,
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
            allow_mixed_parity = bool(rule.get("allow_mixed_parity", False))
            result.extend(
                _build_per_character_parity_entries(
                    binary_string=binary_string,
                    typ=typ,
                    start=start,
                    end=end,
                    character_width=character_width,
                    parity_position=parity_position,
                    gate=gate,
                    allow_mixed_parity=allow_mixed_parity,
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


def parity_score(parity_results: List[Dict]) -> Dict[str, int | bool | Tuple]:
    """Compute scoring metrics for a list of parity results."""
    gated = [p for p in parity_results if p.get("gate", True)]
    gating_present = bool(gated)
    gated_pass = sum(1 for p in gated if p.get("ok") is True)
    gated_fail = sum(1 for p in gated if p.get("ok") is False)
    total_pass = sum(1 for p in parity_results if p.get("ok") is True)
    total_fail = sum(1 for p in parity_results if p.get("ok") is False)
    all_gated_ok = gating_present and gated_fail == 0
    return {
        "gating_present": gating_present,
        "gated_pass": gated_pass,
        "gated_fail": gated_fail,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "all_gated_ok": all_gated_ok,
        "score_tuple": (
            all_gated_ok,
            gated_pass,
            total_pass,
            -gated_fail,
            -total_fail,
        ),
    }


def find_best_offsets(
    binary_string: str,
    fmt: NormalizedFormat,
    step: int = 1,
    top_n: int = 3,
) -> List[Dict]:
    """Search all offsets for the best matching windows using parity scoring."""

    bitlen = fmt.bit_length
    if len(binary_string) < bitlen or step <= 0:
        return []

    candidates: List[Dict] = []
    for offset in range(0, len(binary_string) - bitlen + 1, step):
        window = binary_string[offset : offset + bitlen]
        parity_results = verify_parity(window, fmt)
        stats = parity_score(parity_results)
        score_key = stats["score_tuple"] + (-offset,)
        candidates.append(
            {
                "offset": offset,
                "bits": window,
                "parity": parity_results,
                "stats": stats,
                "score_key": score_key,
            }
        )

    candidates.sort(key=lambda c: c["score_key"], reverse=True)
    return candidates[:top_n]


__all__ = [
    "FORMATS_FILENAME",
    "FormatRepository",
    "NormalizedFormat",
    "FormatValidationError",
    "bits_to_int",
    "extract_bits",
    "extract_fields",
    "merge_formats",
    "normalize_format_entry",
    "normalize_formats",
    "validate_format_entry",
    "parity_even_bit_needed",
    "parity_odd_bit_needed",
    "verify_parity",
    "parity_score",
    "find_best_offsets",
    "load_formats_document",
    "save_formats_document",
    "decode_ansi_bcd5_field",
]
