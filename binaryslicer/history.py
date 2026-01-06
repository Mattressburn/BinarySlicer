from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .decoder import format_binary_groups


@dataclass
class HistoryEntry:
    raw_bits: str
    bit_length: int
    format_name: str
    format_id: Optional[str]
    forced_format_id: Optional[str]
    reverse_bits: bool
    parity_ok: Optional[bool]
    label: str


class HistoryBuffer:
    """Maintain a bounded, deduplicated list of history entries."""

    def __init__(self, max_items: int = 10) -> None:
        self.max_items = max_items
        self._entries: List[HistoryEntry] = []

    @staticmethod
    def _parity_label(parity_ok: Optional[bool]) -> str:
        if parity_ok is True:
            return "OK"
        if parity_ok is False:
            return "FAIL"
        return "—"

    @staticmethod
    def _format_label(format_name: str, forced: bool) -> str:
        if forced:
            return f"{format_name} (forced)"
        return f"{format_name} (auto)"

    @staticmethod
    def _preview_bits(bits: str) -> str:
        display_bits = format_binary_groups(bits, 4)
        return display_bits if len(display_bits) <= 48 else display_bits[:48] + "…"

    def add(
        self,
        *,
        raw_bits: str,
        bit_length: int,
        format_name: str,
        format_id: Optional[str],
        forced_format_id: Optional[str],
        reverse_bits: bool,
        parity_ok: Optional[bool],
    ) -> Optional[HistoryEntry]:
        if not raw_bits:
            return None

        label = " · ".join(
            [
                f"{bit_length}b",
                self._format_label(format_name or "Unknown", bool(forced_format_id)),
                f"Parity {self._parity_label(parity_ok)}",
                self._preview_bits(raw_bits),
            ]
        )

        entry = HistoryEntry(
            raw_bits=raw_bits,
            bit_length=bit_length,
            format_name=format_name or "Unknown",
            format_id=format_id,
            forced_format_id=forced_format_id,
            reverse_bits=reverse_bits,
            parity_ok=parity_ok,
            label=label,
        )

        self._entries = [
            e
            for e in self._entries
            if not (e.raw_bits == raw_bits and e.forced_format_id == forced_format_id and e.reverse_bits == reverse_bits)
        ]
        self._entries.insert(0, entry)
        self._entries = self._entries[: self.max_items]
        return entry

    @property
    def entries(self) -> List[HistoryEntry]:
        return list(self._entries)


__all__ = ["HistoryBuffer", "HistoryEntry"]
