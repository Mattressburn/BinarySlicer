"""Controller boundary for shared BinarySlicer logic.

The Qt UI relies on this module to avoid duplicating business logic that already
exists in the Tkinter implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Sequence

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
    value: str
    hex: str
    view: str = "binary"
    bits: str = ""


@dataclass
class DiagnosticRow:
    type: str
    coverage: str
    status: str
    expected: str
    actual: str
    data_len: str
    parity_bit: str
    gate: str
    status_tag: str


@dataclass
class AnalysisMeta:
    slice_mode: str
    exact_matches: Sequence[str] = field(default_factory=tuple)
    compatible_matches: Sequence[str] = field(default_factory=tuple)
    auto_candidates: Sequence[Mapping] = field(default_factory=tuple)
    offset_used: int | None = None
    parity_ok: bool = False
    rendered: bool = False


@dataclass
class AnalysisResult:
    ok: bool
    error: str | None
    summary: str
    diagnostics_text: str
    table_rows: List[TableRow]
    diagnostics_rows: List[DiagnosticRow]
    csv_rows: List[Dict]
    parity_results: List[Dict]
    input_binary: str
    input_meta: Mapping
    meta: AnalysisMeta


class BinarySlicerController:
    """Stateless-ish controller that can be shared by multiple UIs."""

    def __init__(self, format_repo: FormatRepository | None = None) -> None:
        self.format_repo = format_repo or FormatRepository()

    # ---------------- Public API ----------------
    def analyze_input(
        self, raw: str, *, slice_mode: str = "auto", show_parity_failures: bool = False
    ) -> AnalysisResult:
        """Normalize input, select formats, and render structured results."""

        binary_string, error, input_meta = process_input(raw)
        diagnostics_context: Dict = {
            "input": input_meta,
            "exact_matches": [],
            "compatible_matches": [],
            "rendered": [],
            "auto_candidates": [],
            "slice_mode": slice_mode,
        }

        if error or not binary_string:
            diagnostics_text = build_diagnostics_report(diagnostics_context)
            empty_meta = AnalysisMeta(slice_mode=slice_mode)
            return AnalysisResult(
                ok=False,
                error=error or "Invalid input.",
                summary="",
                diagnostics_text=diagnostics_text,
                table_rows=[],
                diagnostics_rows=[],
                csv_rows=[],
                parity_results=[],
                input_binary=binary_string or "",
                input_meta=input_meta,
                meta=empty_meta,
            )

        exact, compatible = self._detect_formats(binary_string)
        diagnostics_context["exact_matches"] = [name for name, _ in exact]
        diagnostics_context["compatible_matches"] = [name for name, _ in compatible]

        summary_chunks: List[str] = [
            f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n"
        ]
        table_rows: List[TableRow] = []
        csv_rows: List[Dict] = []
        parity_results: List[Dict] = []
        rendered_entries: List[Dict] = []
        auto_candidates_meta: List[Mapping] = []
        offset_used: int | None = None
        rendered_any = False
        def capture_offset(value: int) -> None:
            nonlocal offset_used
            if offset_used is None:
                offset_used = value

        if exact:
            summary_chunks.append("== Exact bit-length matches ==\n")
            rendered_any |= self._render_candidates(
                binary_string,
                exact,
                slice_mode=None,
                show_parity_failures=show_parity_failures,
                summary_chunks=summary_chunks,
                table_rows=table_rows,
                csv_rows=csv_rows,
                parity_results=parity_results,
                rendered_entries=rendered_entries,
            )

        if compatible:
            summary_chunks.append("== Compatible (input longer than known format) ==\n")
            summary_chunks.append("These may indicate framing/padding.\n\n")
            rendered_any |= self._render_candidates(
                binary_string,
                compatible,
                slice_mode=slice_mode,
                show_parity_failures=show_parity_failures,
                summary_chunks=summary_chunks,
                table_rows=table_rows,
                csv_rows=csv_rows,
                parity_results=parity_results,
                rendered_entries=rendered_entries,
                auto_meta=auto_candidates_meta,
                offset_out=capture_offset,
            )

        if not rendered_any:
            summary_chunks.append(
                "No formats passed parity in strict mode.\n"
                "Tip: enable 'Parity diagnostics' to inspect candidates.\n"
            )

        diagnostics_context["rendered"].extend(rendered_entries)
        diagnostics_context["auto_candidates"].extend(auto_candidates_meta)
        diagnostics_text = build_diagnostics_report(diagnostics_context)

        parity_ok = parity_score(parity_results).get("all_gated_ok", False) if parity_results else False
        meta = AnalysisMeta(
            slice_mode=slice_mode,
            exact_matches=diagnostics_context["exact_matches"],
            compatible_matches=diagnostics_context["compatible_matches"],
            auto_candidates=tuple(auto_candidates_meta),
            offset_used=offset_used,
            parity_ok=bool(parity_ok),
            rendered=rendered_any,
        )

        diagnostics_rows = build_diagnostic_rows(parity_results, show_all=show_parity_failures)

        return AnalysisResult(
            ok=rendered_any,
            error=None if rendered_any else "No matching formats passed parity.",
            summary="".join(summary_chunks),
            diagnostics_text=diagnostics_text,
            table_rows=table_rows,
            diagnostics_rows=diagnostics_rows,
            csv_rows=csv_rows,
            parity_results=parity_results,
            input_binary=binary_string,
            input_meta=input_meta,
            meta=meta,
        )

    # ---------------- Internal helpers ----------------
    def _detect_formats(self, binary_string: str):
        exact = []
        compatible = []
        for name, fmt in self.format_repo.formats.items():
            length = fmt.bit_length
            if len(binary_string) == length:
                exact.append((name, fmt))
            elif len(binary_string) > length:
                compatible.append((name, fmt))
        return exact, compatible

    def _render_candidates(
        self,
        binary_string: str,
        candidates: List[tuple[str, NormalizedFormat]],
        *,
        slice_mode: str | None,
        show_parity_failures: bool,
        summary_chunks: List[str],
        table_rows: List[TableRow],
        csv_rows: List[Dict],
        parity_results: List[Dict],
        rendered_entries: List[Dict],
        auto_meta: List[Mapping] | None = None,
        offset_out=None,
    ) -> bool:
        rendered = False
        for name, fmt in candidates:
            if slice_mode == "auto":
                rendered |= self._render_auto_candidates(
                    binary_string,
                    name,
                    fmt,
                    show_parity_failures=show_parity_failures,
                    summary_chunks=summary_chunks,
                    table_rows=table_rows,
                    csv_rows=csv_rows,
                    parity_results=parity_results,
                    rendered_entries=rendered_entries,
                    auto_meta=auto_meta,
                    offset_out=offset_out,
                )
                continue

            use_bits, display_name = self._slice_bits(binary_string, fmt.bit_length, slice_mode, name)
            if not show_parity_failures and not self._parity_all_ok(use_bits, fmt):
                continue
            summary_block, diag_entry, t_rows, csv, parity = self._render_format(use_bits, display_name, fmt, {})
            summary_chunks.append(summary_block)
            table_rows.extend(t_rows)
            csv_rows.extend(csv)
            parity_results.extend(parity)
            rendered_entries.append(diag_entry)
            rendered = True
        return rendered

    def _render_auto_candidates(
        self,
        binary_string: str,
        name: str,
        fmt: NormalizedFormat,
        *,
        show_parity_failures: bool,
        summary_chunks: List[str],
        table_rows: List[TableRow],
        csv_rows: List[Dict],
        parity_results: List[Dict],
        rendered_entries: List[Dict],
        auto_meta: List[Mapping] | None = None,
        offset_out=None,
    ) -> bool:
        rendered = False
        results = find_best_offsets(binary_string, fmt, step=1, top_n=6)
        if not results:
            return False

        best_offset = results[0]["offset"]
        if offset_out:
            offset_out(best_offset)
        if auto_meta is not None:
            auto_meta.extend(results)

        for cand in results:
            stats = cand["stats"]
            parity = cand["parity"]
            if not show_parity_failures and stats["gated_fail"] > 0:
                continue
            display_name = (
                f"{name} (auto offset +{cand['offset']}, "
                f"pass {stats['total_pass']}/{len(parity)}, gated_fail={stats['gated_fail']})"
            )
            summary_block, diag_entry, t_rows, csv, parity_list = self._render_format(
                cand["bits"],
                display_name,
                fmt,
                {"mode": "auto", "offset": cand["offset"], "top_candidates": results},
            )
            summary_chunks.append(summary_block)
            table_rows.extend(t_rows)
            csv_rows.extend(csv)
            parity_results.extend(parity_list)
            rendered_entries.append(diag_entry)
            rendered = True
        return rendered

    def _slice_bits(self, binary_string: str, bit_length: int, slice_mode: str | None, name: str):
        if slice_mode is None:
            return binary_string, name
        if slice_mode == "left":
            return binary_string[:bit_length], f"{name} (leftmost)"
        return binary_string[-bit_length:], f"{name} (rightmost)"

    def _render_format(
        self, binary_string: str, name: str, fmt: NormalizedFormat, meta: Dict | None = None
    ) -> tuple[str, Dict, List[TableRow], List[Dict], List[Dict]]:
        meta = meta or {}
        summary_lines: List[str] = [f"Format: {name}\n"]
        fields = extract_fields(binary_string, fmt)
        table_rows: List[TableRow] = []
        csv_rows: List[Dict] = []

        for field, info in fields.items():
            if info.get("hidden"):
                continue
            start, end = info["range"]
            summary_lines.append(
                f"  {field:14}: {info['int']} (hex {info['hex']}), bits[{info['len']}]={info['bits']}\n"
            )
            table_rows.append(
                TableRow(
                    field=field,
                    range=f"{start}–{end}",
                    value=str(info["int"]),
                    hex=str(info["hex"]),
                    view=info.get("view", "binary"),
                    bits=info.get("bits", ""),
                )
            )
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
            "meta": meta,
        }

        return "\n".join(summary_lines), diag_entry, table_rows, csv_rows, parity

    @staticmethod
    def _parity_all_ok(binary_string: str, fmt: NormalizedFormat) -> bool:
        parity = verify_parity(binary_string, fmt)
        if not parity:
            return True
        for result in parity:
            if result.get("gate", True) and result.get("ok") is False:
                return False
        return True


def build_diagnostic_rows(parity_results: Iterable[Mapping], *, show_all: bool = False) -> List[DiagnosticRow]:
    """Transform parity results into rows suitable for tabular display."""

    rows: List[DiagnosticRow] = []
    visible_idx = 0
    for result in parity_results or []:
        ok = result.get("ok")
        gate = result.get("gate", True)
        if not show_all and ok is not False:
            continue
        coverage = result.get("coverage") or ("?", "?")
        coverage_text = f"{coverage[0]}–{coverage[1]}"
        status_text = "OK" if ok is True else ("FAIL" if gate else "Advisory") if ok is False else "Not evaluated"
        parity_bit = result.get("parity_bit")
        parity_text = "-" if parity_bit is None else str(parity_bit)
        status_tag = "status_ok" if ok is True else ("status_fail" if gate else "status_warn") if ok is False else "status_neutral"
        rows.append(
            DiagnosticRow(
                type=result.get("label") or result.get("type", ""),
                coverage=coverage_text,
                status=status_text,
                expected=str(result.get("expected", "")),
                actual=str(result.get("actual", "")),
                data_len=str(result.get("data_len", "")),
                parity_bit=parity_text,
                gate="Yes" if gate else "Advisory",
                status_tag=status_tag,
            )
        )
        visible_idx += 1

    if visible_idx == 0:
        rows.append(
            DiagnosticRow(
                type="No parity failures to show" if not show_all else "No parity checks",
                coverage="",
                status="OK" if not show_all else "Not evaluated",
                expected="",
                actual="",
                data_len="",
                parity_bit="",
                gate="",
                status_tag="status_neutral",
            )
        )
    return rows


__all__ = [
    "AnalysisMeta",
    "AnalysisResult",
    "BinarySlicerController",
    "DiagnosticRow",
    "TableRow",
    "build_diagnostic_rows",
]
