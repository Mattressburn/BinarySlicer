"""Input normalization helpers for BinarySlicer."""

from __future__ import annotations

import textwrap

HEX_CHARS = set("0123456789abcdefABCDEF")


def clean_input(value: str) -> str:
    return value.strip()


def is_binary(value: str) -> bool:
    return bool(value) and all(ch in "01" for ch in value)


def is_hex(value: str) -> bool:
    return bool(value) and all(ch in HEX_CHARS for ch in value)


def hex_to_binary(hex_string: str) -> str | None:
    try:
        return bin(int(hex_string, 16))[2:].zfill(len(hex_string) * 4)
    except ValueError:
        return None


def process_input(raw: str):
    cleaned = clean_input(raw)
    cleaned = cleaned.replace(" ", "").replace("-", "").replace("_", "")
    if cleaned.startswith(("0x", "0X")):
        cleaned = cleaned[2:]

    meta = {
        "raw_length": len(raw or ""),
        "cleaned_length": len(cleaned),
        "cleaned": cleaned,
        "input_type": "unknown",
        "normalized_length": 0,
    }

    if is_binary(cleaned):
        meta.update({"input_type": "binary", "normalized_length": len(cleaned)})
        return cleaned, None, meta
    if is_hex(cleaned):
        converted = hex_to_binary(cleaned)
        if converted is None:
            return None, "Invalid hex input.", meta
        meta.update({"input_type": "hex", "normalized_length": len(converted)})
        return converted, None, meta
    return None, "Input must be hex or binary (e.g., 0x1A2B, 1100101).", meta


def format_binary_groups(bits: str, group: int = 4) -> str:
    if group <= 0:
        return bits
    remainder = len(bits) % group
    leading = "" if remainder == 0 else bits[:remainder] + " "
    rest = bits[remainder:]
    return leading + " ".join(textwrap.wrap(rest, group)) if rest else bits


__all__ = [
    "clean_input",
    "is_binary",
    "is_hex",
    "hex_to_binary",
    "process_input",
    "format_binary_groups",
]
