"""UI-agnostic controller for BinarySlicer analysis."""

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
    field: str
    range: str
    value: int | str
    hex: str
    bits: str
    hidden: bool = False


@dataclass
class AnalysisOptions:
    slice_mode: str = "auto"  # one of: auto, left, right, None (exact)
    show_parity_failures: bool = False


@dataclass
class AnalysisResult:
    success: bool
    error: Optional[str] = None
    summary_text: str = ""
    diagnostics_text: str = ""
    table_rows: List[TableRow] = field(default_factory=list)
    csv_rows: List[Dict[str, str | int]] = field(default_factory=list)
    parity_results: List[Dict] = field(default_factory=list)
    parity_summary: Dict[str, int | bool] = field(default_factory=dict)
    exact_matches: List[str] = field(default_factory=list)
    compatible_matches: List[str] = field(default_factory=list)
    binary_string: str = ""
    input_meta: Dict = field(default_factory=dict)
    rendered: List[Dict] = field(default_factory=list)


class Controller:
    """Encapsulates BinarySlicer analysis logic for reuse across UIs."""

    def __init__(self, format_repo: FormatRepository | None = None) -> None:
        self.format_repo = format_repo or FormatRepository()

    # Public API ---------------------------------------------------------
    def analyze_input(self, raw_input: str, options: AnalysisOptions | None = None) -> AnalysisResult:
        opts = options or AnalysisOptions()
        binary_string, error, input_meta = process_input(raw_input)
        if error:
            return AnalysisResult(success=False, error=error, input_meta=input_meta)

        summary_lines: List[str] = [f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n"]

        exact, compatible = self._detect_formats(binary_string)
        diagnostics_context: Dict = {
            "input": input_meta,
            "exact_matches": [name for name, _ in exact],
            "compatible_matches": [name for name, _ in compatible],
            "rendered": [],
            "auto_candidates": [],
            "slice_mode": opts.slice_mode,
        }

        if not exact and not compatible:
            summary_lines.append("No matching formats found.\n")
            diagnostics_text = build_diagnostics_report(diagnostics_context)
            return AnalysisResult(
                success=True,
                summary_text="".join(summary_lines),
                diagnostics_text=diagnostics_text,
                binary_string=binary_string,
                input_meta=input_meta,
                exact_matches=[name for name, _ in exact],
                compatible_matches=[name for name, _ in compatible],
            )

        rendered_any = False
        table_rows: List[TableRow] = []
        csv_rows: List[Dict[str, str | int]] = []
        parity_results: List[Dict] = []

        if exact:
            summary_lines.append("== Exact bit-length matches ==\n")
            rendered, diag_entries, chunks, tables, csv_data, parity_data = self._render_candidates(
                binary_string, exact, slice_mode=None, show_parity_failures=opts.show_parity_failures
            )
            diagnostics_context["rendered"].extend(diag_entries)
            summary_lines.extend(chunks)
            table_rows.extend(tables)
            csv_rows.extend(csv_data)
            parity_results.extend(parity_data)
            rendered_any |= rendered

        if compatible:
            summary_lines.append("== Compatible (input longer than known format) ==\n")
            summary_lines.append("These may indicate framing/padding.\n\n")
            rendered, diag_entries, chunks, tables, csv_data, parity_data = self._render_candidates(
                binary_string,
                compatible,
                slice_mode=opts.slice_mode,
                show_parity_failures=opts.show_parity_failures,
            )
            diagnostics_context["rendered"].extend(diag_entries)
            summary_lines.extend(chunks)
            table_rows.extend(tables)
            csv_rows.extend(csv_data)
            parity_results.extend(parity_data)
            rendered_any |= rendered

        if not rendered_any:
            summary_lines.append(
                "No formats passed parity in strict mode.\n"
                "Tip: Enable 'Parity diagnostics' to inspect candidates.\n"
            )

        diagnostics_text = build_diagnostics_report(diagnostics_context)
        parity_summary = parity_score(parity_results) if parity_results else {}

        return AnalysisResult(
            success=True,
            summary_text="".join(summary_lines),
            diagnostics_text=diagnostics_text,
            table_rows=table_rows,
            csv_rows=csv_rows,
            parity_results=parity_results,
            parity_summary=parity_summary,
            exact_matches=[name for name, _ in exact],
            compatible_matches=[name for name, _ in compatible],
            binary_string=binary_string,
            input_meta=input_meta,
            rendered=diagnostics_context["rendered"],
        )

    # Internal helpers ---------------------------------------------------
    def _detect_formats(self, binary_string: str) -> Tuple[List[Tuple[str, NormalizedFormat]], List[Tuple[str, NormalizedFormat]]]:
        exact: List[Tuple[str, NormalizedFormat]] = []
        compatible: List[Tuple[str, NormalizedFormat]] = []
        for name, fmt in self.format_repo.formats.items():
            bitlen = fmt.bit_length
            if len(binary_string) == bitlen:
                exact.append((name, fmt))
            elif len(binary_string) > bitlen:
                compatible.append((name, fmt))
        return exact, compatible

    def _render_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        *,
        slice_mode: Optional[str],
        show_parity_failures: bool,
    ) -> Tuple[bool, List[Dict], List[str], List[TableRow], List[Dict[str, str | int]], List[Dict]]:
        if slice_mode == "auto":
            return self._render_auto_candidates(binary_string, candidates, show_parity_failures)

        rendered = False
        diagnostics: List[Dict] = []
        summaries: List[str] = []
        tables: List[TableRow] = []
        csv_rows: List[Dict[str, str | int]] = []
        parity_results: List[Dict] = []

        for name, fmt in candidates:
            bit_length = fmt.bit_length
            if slice_mode is None:
                use_bits = binary_string
                display_name = name
            else:
                use_bits = binary_string[:bit_length] if slice_mode == "left" else binary_string[-bit_length:]
                suffix = "leftmost" if slice_mode == "left" else "rightmost"
                display_name = f"{name} ({suffix})"

            if not show_parity_failures and not self._parity_all_ok(use_bits, fmt):
                continue

            summary_block, diag_entry, table_rows, csv_data, parity_data = self._render_format(
                use_bits, display_name, fmt, {"mode": slice_mode}
            )
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            tables.extend(table_rows)
            csv_rows.extend(csv_data)
            parity_results.extend(parity_data)
            rendered = True
        return rendered, diagnostics, summaries, tables, csv_rows, parity_results

    def _render_auto_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        show_parity_failures: bool,
    ) -> Tuple[bool, List[Dict], List[str], List[TableRow], List[Dict[str, str | int]], List[Dict]]:
        rendered = False
        diagnostics: List[Dict] = []
        summaries: List[str] = []
        tables: List[TableRow] = []
        csv_rows: List[Dict[str, str | int]] = []
        parity_results: List[Dict] = []
        all_results: List[Dict] = []

        for name, fmt in candidates:
            for cand in find_best_offsets(binary_string, fmt, step=1, top_n=3):
                all_results.append({"name": name, "fmt": fmt, "candidate": cand})

        if not all_results:
            return False, diagnostics, summaries, tables, csv_rows, parity_results

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
            summary_block, diag_entry, table_rows, csv_data, parity_data = self._render_format(
                cand["bits"],
                display_name,
                entry["fmt"],
                {"mode": "auto", "offset": cand["offset"], "top_candidates": all_results[:limit]},
            )
            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            tables.extend(table_rows)
            csv_rows.extend(csv_data)
            parity_results.extend(parity_data)
            rendered = True

        return rendered, diagnostics, summaries, tables, csv_rows, parity_results

    def _render_format(
        self, binary_string: str, name: str, fmt: NormalizedFormat, meta: Optional[Mapping] = None
    ) -> Tuple[str, Dict, List[TableRow], List[Dict[str, str | int]], List[Dict]]:
        metadata = dict(meta or {})
        summary_lines: List[str] = [f"Format: {name}\n"]
        table_rows: List[TableRow] = []
        csv_rows: List[Dict[str, str | int]] = []

        fields = extract_fields(binary_string, fmt)
        for field_name, field_meta in fields.items():
            if field_meta.get("hidden"):
                continue
            start, end = field_meta["range"]
            range_text = f"{start}–{end}"
            summary_lines.append(
                f"  {field_name:14}: {field_meta['int']} (hex {field_meta['hex']}), bits[{field_meta['len']}]={field_meta['bits']}\n"
            )
            table_rows.append(
                TableRow(
                    field=field_name,
                    range=range_text,
                    value=field_meta["int"],
                    hex=field_meta["hex"],
                    bits=field_meta["bits"],
                )
            )
            csv_rows.append(
                {
                    "Format": name,
                    "Field": field_name,
                    "Value": field_meta["int"],
                    "Hex": field_meta["hex"],
                    "BitLength": field_meta["len"],
                    "Bits": field_meta["bits"],
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

        summary_lines.append("\n")

        diag_entry = {
            "name": name,
            "bit_length": len(binary_string),
            "parity": parity,
            "parity_stats": parity_score(parity) if parity else None,
            "meta": metadata,
        }

        return "\n".join(summary_lines), diag_entry, table_rows, csv_rows, parity

    @staticmethod
    def _parity_all_ok(binary_string: str, fmt: NormalizedFormat) -> bool:
        parity = verify_parity(binary_string, fmt)
        if not parity:
            return True
        return all(result.get("ok") is not False or not result.get("gate", True) for result in parity)


__all__ = [
    "AnalysisOptions",
    "AnalysisResult",
    "Controller",
    "TableRow",
]

