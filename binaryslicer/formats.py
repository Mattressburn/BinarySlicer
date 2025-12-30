"""Format loading, normalization, and parity helpers."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, MutableMapping, Optional, Sequence, Tuple

from .config import load_json, save_json
from .resources import default_formats

FORMATS_FILENAME = "formats.json"

FieldRange = Tuple[int, int]


@dataclass
class NormalizedFormat:
    name: str
    bit_length: int
    fields: Dict[str, FieldRange]
    parity_coverage: List[Dict[str, List[FieldRange]]]
    raw: Dict


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


def normalize_format_entry(entry: Dict) -> NormalizedFormat:
    name = entry.get("name", "Format")
    bitlen = int(entry.get("bit_length", 0))
    fields = {fld.get("name", "Field"): _coerce_range(fld) for fld in entry.get("fields", [])}
    parity_cov: List[Dict[str, List[FieldRange]]] = []
    for rule in entry.get("parity", []):
        typ = str(rule.get("type", "even")).lower()
        ranges = [_coerce_range(r) for r in rule.get("ranges", []) if r is not None]
        if ranges:
            parity_cov.append({"type": typ, "ranges": ranges})
    return NormalizedFormat(name=name, bit_length=bitlen, fields=fields, parity_coverage=parity_cov, raw=entry)


def normalize_formats(doc: Dict) -> Dict[str, NormalizedFormat]:
    result: Dict[str, NormalizedFormat] = {}
    for entry in doc.get("formats", []):
        fmt = normalize_format_entry(entry)
        result[fmt.name] = fmt
    return result


def extract_bits(binary_string: str, start: int, end: int) -> str:
    return binary_string[start : end + 1]


def bits_to_int(bits: str) -> int:
    return int(bits, 2) if bits else 0


def extract_fields(binary_string: str, fmt: NormalizedFormat) -> Dict[str, Dict]:
    fields: Dict[str, Dict] = {}
    for field, (start, end) in fmt.fields.items():
        bits = extract_bits(binary_string, start, end)
        value = bits_to_int(bits)
        fields[field] = {
            "bits": bits,
            "int": value,
            "hex": f"0x{value:X}",
            "len": end - start + 1,
            "range": (start, end),
        }
    return fields


def _parse_parity_range(r) -> Optional[FieldRange]:
    if isinstance(r, dict) and "start" in r and "end" in r:
        return int(r["start"]), int(r["end"])
    if isinstance(r, (list, tuple)) and len(r) >= 2:
        return int(r[0]), int(r[1])
    return None


def _normalize_parity_coverage(coverage):
    if isinstance(coverage, dict):
        rules = []
        for typ in ("even", "odd"):
            ranges = coverage.get(typ)
            if not ranges:
                continue
            normalized = [ranges] if isinstance(ranges, dict) else list(ranges)
            rules.append({"type": typ, "ranges": normalized})
        return rules
    if isinstance(coverage, list):
        return coverage
    return []


def parity_even_bit_needed(bits: str) -> int:
    return 0 if bits.count("1") % 2 == 0 else 1


def parity_odd_bit_needed(bits: str) -> int:
    return 1 if bits.count("1") % 2 == 0 else 0


def _build_parity_entry(binary_string: str, typ: str, start: int, end: int) -> Dict:
    data_bits = extract_bits(binary_string, start, end)
    expected = parity_even_bit_needed(data_bits) if typ == "even" else parity_odd_bit_needed(data_bits)
    return {
        "label": "Even Parity" if typ == "even" else "Odd Parity",
        "type": typ,
        "coverage": (start, end),
        "expected": expected,
        "actual": None,
        "ok": None,
        "data_len": len(data_bits),
    }


def verify_parity(binary_string: str, fmt: NormalizedFormat) -> List[Dict]:
    coverage = fmt.parity_coverage or fmt.raw.get("parity")
    if not coverage:
        return []
    normalized = _normalize_parity_coverage(coverage)
    result: List[Dict] = []
    for rule in normalized:
        typ = str(rule.get("type", "even")).lower()
        for rng in rule.get("ranges", []):
            parsed = _parse_parity_range(rng)
            if not parsed:
                continue
            start, end = parsed
            result.append(_build_parity_entry(binary_string, typ, start, end))
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
]
