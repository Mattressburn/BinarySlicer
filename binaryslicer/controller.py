"""Controller boundary for BinarySlicer business logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .decoder import format_binary_groups, process_input
from .diagnostics import build_diagnostics_report
from .formats import (
    FormatRepository,
    NormalizedFormat,
    extract_fields,
    find_best_offsets,
    parity_score,
    verify_parity,
)


@dataclass
class TableRow:
    """Row for the primary results table."""

    field: str
    range: str
    value: str
    hex: str
    format_name: str


@dataclass
class ParityRow:
    """Row for parity diagnostics."""

    label: str
    coverage: str
    status: str
    expected: str
    actual: str
    data_len: str
    parity_bit: str
    gate: str
    ok: Optional[bool]


@dataclass
class AnalysisResult:
    """Container for controller results."""

    summary: str = ""
    diagnostics_text: str = ""
    table_rows: List[TableRow] = field(default_factory=list)
    parity_rows: List[ParityRow] = field(default_factory=list)
    csv_rows: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    input_meta: Dict = field(default_factory=dict)
    formats_rendered: List[str] = field(default_factory=list)
    parity_ok: Optional[bool] = None
    parity_stats: Dict[str, int] = field(default_factory=dict)
    best_offset: Optional[int] = None
    slice_mode: Optional[str] = None
    bit_length: int = 0


class Controller:
    """Encapsulates BinarySlicer parsing and diagnostics."""

    def __init__(self, repo: Optional[FormatRepository] = None) -> None:
        self.repo = repo or FormatRepository()

    def analyze_input(
        self, raw_input: str, *, slice_mode: str = "auto", show_parity_failures: bool = False
    ) -> AnalysisResult:
        """Normalize input, select formats, and render results."""

        binary_string, error, input_meta = process_input(raw_input)
        result = AnalysisResult(error=error, input_meta=input_meta, slice_mode=slice_mode)
        if error or not binary_string:
            return result

        result.bit_length = len(binary_string)
        exact, compatible = self._detect_formats(binary_string)

        summary_lines: List[str] = []
        summary_lines.append(f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n")

        diagnostics_context: Dict = {
            "input": input_meta,
            "exact_matches": [name for name, _ in exact],
            "compatible_matches": [name for name, _ in compatible],
            "rendered": [],
            "auto_candidates": [],
            "slice_mode": slice_mode,
        }

        if not exact and not compatible:
            summary_lines.append("No matching formats found.\n")
            result.summary = "".join(summary_lines)
            result.diagnostics_text = build_diagnostics_report(diagnostics_context)
            return result

        diag_entries: List[Dict] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}
        rendered_any = False

        if exact:
            summary_lines.append("== Exact bit-length matches ==\n")
            rendered, diag_list, chunks, csv_rows, table_rows, parity_map = self._render_candidates(
                binary_string, exact, None, show_parity_failures
            )
            if rendered:
                diag_entries.extend(diag_list)
                summary_lines.extend(chunks)
                result.csv_rows.extend(csv_rows)
                result.table_rows.extend(table_rows)
                parity_rows_map.update(parity_map)
                rendered_any = True

        if compatible:
            summary_lines.append("== Compatible (input longer than known format) ==\n")
            summary_lines.append("These may indicate framing/padding.\n\n")
            rendered, diag_list, chunks, csv_rows, table_rows, parity_map = self._render_candidates(
                binary_string, compatible, slice_mode, show_parity_failures
            )
            if rendered:
                diag_entries.extend(diag_list)
                summary_lines.extend(chunks)
                result.csv_rows.extend(csv_rows)
                result.table_rows.extend(table_rows)
                parity_rows_map.update(parity_map)
                rendered_any = True

        if not rendered_any:
            summary_lines.append(
                "No formats passed parity in strict mode.\n"
                "Tip: enable parity diagnostics to inspect gated failures.\n"
            )

        diagnostics_context["rendered"].extend(diag_entries)
        result.formats_rendered = [entry.get("name") for entry in diag_entries if entry.get("name")]
        result.summary = "".join(summary_lines)
        result.diagnostics_text = build_diagnostics_report(diagnostics_context)

        best_entry = self._pick_best_entry(diag_entries)
        if best_entry:
            parity = best_entry.get("parity") or []
            stats = parity_score(parity)
            result.parity_stats = stats
            result.parity_ok = stats["gated_fail"] == 0 if stats["gating_present"] else None
            result.best_offset = best_entry.get("meta", {}).get("offset")
            parity_rows = parity_rows_map.get(best_entry["name"], [])
            if not show_parity_failures:
                parity_rows = [row for row in parity_rows if row.ok is False]
            result.parity_rows = parity_rows or parity_rows_map.get(best_entry["name"], [])

        return result

    def _detect_formats(self, binary_string: str) -> Tuple[List[Tuple[str, NormalizedFormat]], List[Tuple[str, NormalizedFormat]]]:
        exact: List[Tuple[str, NormalizedFormat]] = []
        compatible: List[Tuple[str, NormalizedFormat]] = []
        for name, fmt in self.repo.formats.items():
            length = fmt.bit_length
            if len(binary_string) == length:
                exact.append((name, fmt))
            elif len(binary_string) > length:
                compatible.append((name, fmt))
        return exact, compatible

    def _render_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        slice_mode: Optional[str],
        show_parity_failures: bool,
    ) -> Tuple[bool, List[Dict], List[str], List[Dict], List[TableRow], Dict[str, List[ParityRow]]]:
        rendered = False
        diagnostics: List[Dict] = []
        summaries: List[str] = []
        csv_rows: List[Dict] = []
        table_rows: List[TableRow] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}

        if slice_mode == "auto":
            return self._render_auto_candidates(binary_string, candidates, show_parity_failures)

        for name, fmt in candidates:
            use_bits, display_name = self._slice_bits(binary_string, fmt.bit_length, slice_mode, name)
            if not show_parity_failures and not self._parity_all_ok(use_bits, fmt):
                continue
            summary_block, diag_entry, rows, csv_data, parity_rows = self._render_format(
                use_bits,
                display_name,
                fmt,
                {"mode": slice_mode},
            )
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            csv_rows.extend(csv_data)
            table_rows.extend(rows)
            parity_rows_map[diag_entry["name"]] = parity_rows
            rendered = True

        return rendered, diagnostics, summaries, csv_rows, table_rows, parity_rows_map

    def _render_auto_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        show_parity_failures: bool,
    ) -> Tuple[bool, List[Dict], List[str], List[Dict], List[TableRow], Dict[str, List[ParityRow]]]:
        rendered = False
        diagnostics: List[Dict] = []
        summaries: List[str] = []
        csv_rows: List[Dict] = []
        table_rows: List[TableRow] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}
        all_results: List[Dict] = []

        for name, fmt in candidates:
            best = find_best_offsets(binary_string, fmt, step=1, top_n=3)
            for candidate in best:
                all_results.append({"name": name, "fmt": fmt, "candidate": candidate})

        if not all_results:
            return False, diagnostics, summaries, csv_rows, table_rows, parity_rows_map

        all_results.sort(key=lambda c: c["candidate"]["score_key"], reverse=True)
        limit = max(3, min(len(all_results), 10))
        for entry in all_results[:limit]:
            cand = entry["candidate"]
            stats = cand["stats"]
            parity = cand["parity"]
            if not show_parity_failures and stats["gated_fail"] > 0:
                continue
            display_name = (
                f"{entry['name']} (auto offset +{cand['offset']}, "
                f"pass {stats['total_pass']}/{len(parity)}, gated_fail={stats['gated_fail']})"
            )
            summary_block, diag_entry, rows, csv_data, parity_rows = self._render_format(
                cand["bits"],
                display_name,
                entry["fmt"],
                {
                    "mode": "auto",
                    "offset": cand["offset"],
                    "top_candidates": all_results[:limit],
                },
            )
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            csv_rows.extend(csv_data)
            table_rows.extend(rows)
            parity_rows_map[diag_entry["name"]] = parity_rows
            rendered = True

        return rendered, diagnostics, summaries, csv_rows, table_rows, parity_rows_map

    @staticmethod
    def _slice_bits(bits: str, width: int, mode: Optional[str], name: str) -> Tuple[str, str]:
        if mode == "left":
            return bits[:width], name + " (leftmost)"
        if mode == "right":
            return bits[-width:], name + " (rightmost)"
        return bits, name

    @staticmethod
    def _parity_all_ok(binary_string: str, fmt: NormalizedFormat) -> bool:
        parity = verify_parity(binary_string, fmt)
        if not parity:
            return True
        for result in parity:
            if result.get("gate", True) and result.get("ok") is False:
                return False
        return True

    def _render_format(
        self, binary_string: str, name: str, fmt: NormalizedFormat, meta: Optional[Mapping] = None
    ) -> Tuple[str, Dict, List[TableRow], List[Dict], List[ParityRow]]:
        meta = dict(meta or {})
        summary_lines: List[str] = [f"Format: {name}\n"]
        fields = extract_fields(binary_string, fmt)
        table_rows: List[TableRow] = []
        csv_rows: List[Dict] = []

        for field, info in fields.items():
            if info.get("hidden"):
                continue
            start, end = info["range"]
            range_text = f"{start}–{end}"
            summary_lines.append(f"  {field:14}: {info['int']} (hex {info['hex']}), bits[{info['len']}]={info['bits']}\n")
            table_rows.append(TableRow(field=field, range=range_text, value=str(info["int"]), hex=info["hex"], format_name=name))
            csv_rows.append(
                {
                    "Format": name,
                    "Field": field,
                    "Value": info["int"],
                    "Hex": info["hex"],
                    "BitLength": info["len"],
                    "Bits": info["bits"],
                }
            )

        parity = verify_parity(binary_string, fmt)
        parity_rows = self._render_parity_rows(parity)
        if parity:
            for result in parity:
                status = "OK" if result.get("ok") else "FAIL" if result.get("ok") is False else "(not evaluated)"
                note = " (advisory)" if not result.get("gate", True) else ""
                parity_loc = f"; parity_bit={result.get('parity_bit')}" if result.get("parity_bit") is not None else ""
                summary_lines.append(
                    f"  Parity {result['type']:4} {result['coverage'][0]}–{result['coverage'][1]}: {status}{note} "
                    f"(expected {result.get('expected')}, actual {result.get('actual')}; data_len={result.get('data_len')}{parity_loc})\n"
                )
        summary_lines.append("\n")

        return "\n".join(summary_lines), {
            "name": name,
            "bit_length": len(binary_string),
            "parity": parity,
            "parity_stats": parity_score(parity) if parity else None,
            "meta": meta,
        }, table_rows, csv_rows, parity_rows

    @staticmethod
    def _render_parity_rows(parity: Iterable[Mapping]) -> List[ParityRow]:
        rows: List[ParityRow] = []
        for result in parity or []:
            coverage = result.get("coverage") or ("?", "?")
            coverage_text = f"{coverage[0]}–{coverage[1]}"
            parity_bit = result.get("parity_bit")
            values = ParityRow(
                label=str(result.get("label") or result.get("type") or ""),
                coverage=coverage_text,
                status="OK" if result.get("ok") else "FAIL" if result.get("ok") is False else "Not evaluated",
                expected=str(result.get("expected", "")),
                actual=str(result.get("actual", "")),
                data_len=str(result.get("data_len", "")),
                parity_bit="-" if parity_bit is None else str(parity_bit),
                gate="Yes" if result.get("gate", True) else "Advisory",
                ok=result.get("ok"),
            )
            rows.append(values)
        return rows

    @staticmethod
    def _pick_best_entry(entries: Sequence[Mapping]) -> Optional[Mapping]:
        def score(entry: Mapping) -> Tuple:
            stats = entry.get("parity_stats") or {}
            return stats.get("score_tuple") or (False, 0, 0, 0, 0)

        if not entries:
            return None
        return max(entries, key=score)


__all__ = ["Controller", "AnalysisResult", "TableRow", "ParityRow"]
