"""Controller boundary for UI layers.

The controller encapsulates the BinarySlicer analysis workflow so that
multiple frontends (Tk, Qt) can drive the same business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

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
    bits: str


@dataclass
class AnalysisResult:
    success: bool
    error: Optional[str]
    binary: Optional[str]
    summary_text: str
    diagnostics_text: str
    table_rows: List[TableRow] = field(default_factory=list)
    parity_results: List[dict] = field(default_factory=list)
    primary_format: Optional[str] = None
    offset: Optional[int] = None
    input_meta: dict = field(default_factory=dict)
    exact_matches: List[str] = field(default_factory=list)
    compatible_matches: List[str] = field(default_factory=list)
    slice_mode: str = "auto"
    rendered: List[dict] = field(default_factory=list)
    parity_ok: Optional[bool] = None


def _detect_formats(binary_string: str, formats: dict[str, NormalizedFormat]) -> Tuple[list, list]:
    exact = []
    compatible = []
    for name, fmt in formats.items():
        bit_len = fmt.bit_length
        if len(binary_string) == bit_len:
            exact.append((name, fmt))
        elif len(binary_string) > bit_len:
            compatible.append((name, fmt))
    return exact, compatible


def _parity_all_ok(parity: Sequence[dict]) -> bool:
    if not parity:
        return True
    for result in parity:
        if result.get("gate", True) and result.get("ok") is False:
            return False
    return True


def _render_format(
    binary_string: str, name: str, fmt: NormalizedFormat, meta: Optional[dict] = None
) -> tuple[str, dict, List[TableRow]]:
    meta = meta or {}
    summary_lines: List[str] = [f"Format: {name}\n"]
    fields = extract_fields(binary_string, fmt)
    rows: List[TableRow] = []
    for field, fmeta in fields.items():
        if fmeta.get("hidden"):
            continue
        start, end = fmeta["range"]
        summary_lines.append(
            f"  {field:14}: {fmeta['int']} (hex {fmeta['hex']}), bits[{fmeta['len']}]={fmeta['bits']}\n"
        )
        rows.append(
            TableRow(
                field=field,
                range=f"{start}–{end}",
                value=str(fmeta["int"]),
                hex=fmeta["hex"],
                bits=fmeta["bits"],
            )
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

    stats = parity_score(parity) if parity else None
    return "\n".join(summary_lines), {
        "name": name,
        "bit_length": len(binary_string),
        "parity": parity,
        "parity_stats": stats,
        "meta": meta,
    }, rows


def _render_auto_candidates(
    binary_string: str,
    candidates: list[tuple[str, NormalizedFormat]],
    show_parity_failures: bool,
) -> tuple[bool, list[dict], list[str], List[TableRow]]:
    rendered = False
    diagnostics: list[dict] = []
    summaries: list[str] = []
    rows: List[TableRow] = []
    all_results: list[dict] = []

    for name, fmt in candidates:
        best = find_best_offsets(binary_string, fmt, step=1, top_n=3)
        for cand in best:
            all_results.append({"name": name, "fmt": fmt, "candidate": cand})

    if not all_results:
        return False, diagnostics, summaries, rows

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
        summary_block, diag_entry, row_entries = _render_format(
            cand["bits"],
            display_name,
            entry["fmt"],
            {"mode": "auto", "offset": cand["offset"], "top_candidates": all_results[:limit]},
        )
        summaries.append(summary_block)
        diagnostics.append(diag_entry)
        rows.extend(row_entries)
        rendered = True
    return rendered, diagnostics, summaries, rows


def _render_candidates(
    binary_string: str,
    candidates: list[tuple[str, NormalizedFormat]],
    slice_mode: Optional[str],
    show_parity_failures: bool,
) -> tuple[bool, list[dict], list[str], List[TableRow]]:
    if slice_mode == "auto":
        return _render_auto_candidates(binary_string, candidates, show_parity_failures)

    rendered = False
    diagnostics: list[dict] = []
    summaries: list[str] = []
    rows: List[TableRow] = []

    for name, fmt in candidates:
        bit_length = fmt.bit_length
        if slice_mode is None:
            use_bits = binary_string
            display_name = name
        else:
            use_bits = binary_string[:bit_length] if slice_mode == "left" else binary_string[-bit_length:]
            display_name = name + (" (leftmost)" if slice_mode == "left" else " (rightmost)")
        parity = verify_parity(use_bits, fmt)
        if not show_parity_failures and not _parity_all_ok(parity):
            continue
        summary_block, diag_entry, row_entries = _render_format(use_bits, display_name, fmt, {"mode": slice_mode})
        summaries.append(summary_block)
        diagnostics.append(diag_entry)
        rows.extend(row_entries)
        rendered = True
    return rendered, diagnostics, summaries, rows


def _choose_primary_parity(rendered: Iterable[dict]) -> tuple[list[dict], Optional[str], Optional[int]]:
    best_entry = None
    best_score = None
    for entry in rendered:
        stats = entry.get("parity_stats") or parity_score(entry.get("parity") or [])
        score_key = (
            stats.get("all_gated_ok", False),
            stats.get("gated_pass", 0),
            stats.get("total_pass", 0),
            -stats.get("gated_fail", 0),
            -stats.get("total_fail", 0),
        )
        if best_score is None or score_key > best_score:
            best_score = score_key
            best_entry = entry

    if not best_entry:
        return [], None, None
    parity = best_entry.get("parity") or []
    name = best_entry.get("name")
    offset = None
    meta = best_entry.get("meta") or {}
    if meta.get("mode") == "auto":
        offset = meta.get("offset")
    return parity, name, offset


def analyze_input(
    input_data: str,
    *,
    show_parity_failures: bool = False,
    slice_mode: str = "auto",
    format_repo: Optional[FormatRepository] = None,
) -> AnalysisResult:
    """Analyze user input and return a structured result for UI layers."""

    repo = format_repo or FormatRepository()
    binary_string, error, input_meta = process_input(input_data)

    summary_lines: list[str] = []
    table_rows: List[TableRow] = []
    diagnostics_rendered: list[dict] = []
    primary_format = None
    offset = None

    if error or not binary_string:
        diagnostics_text = build_diagnostics_report(
            {
                "input": input_meta,
                "exact_matches": [],
                "compatible_matches": [],
                "rendered": [],
                "slice_mode": slice_mode,
            }
        )
        return AnalysisResult(
            success=False,
            error=error or "No input provided.",
            binary=None,
            summary_text="",
            diagnostics_text=diagnostics_text,
            table_rows=[],
            parity_results=[],
            primary_format=None,
            offset=None,
            input_meta=input_meta,
            exact_matches=[],
            compatible_matches=[],
            slice_mode=slice_mode,
            rendered=[],
            parity_ok=None,
        )

    summary_lines.append(f"Binary ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n")
    exact, compatible = _detect_formats(binary_string, repo.formats)
    diagnostics_context: dict = {
        "input": input_meta,
        "exact_matches": [name for name, _ in exact],
        "compatible_matches": [name for name, _ in compatible],
        "rendered": [],
        "auto_candidates": [],
        "slice_mode": slice_mode,
    }

    if not exact and not compatible:
        summary_lines.append("No matching formats found.\n")
        diagnostics_text = build_diagnostics_report(diagnostics_context)
        return AnalysisResult(
            success=True,
            error=None,
            binary=binary_string,
            summary_text="".join(summary_lines),
            diagnostics_text=diagnostics_text,
            table_rows=[],
            parity_results=[],
            primary_format=None,
            offset=None,
            input_meta=input_meta,
            exact_matches=diagnostics_context["exact_matches"],
            compatible_matches=diagnostics_context["compatible_matches"],
            slice_mode=slice_mode,
            rendered=[],
            parity_ok=None,
        )

    rendered_any = False
    if exact:
        summary_lines.append("== Exact bit-length matches ==\n")
        rendered, diag, chunks, rows = _render_candidates(
            binary_string, exact, slice_mode=None, show_parity_failures=show_parity_failures
        )
        diagnostics_rendered.extend(diag)
        summary_lines.extend(chunks)
        table_rows.extend(rows)
        rendered_any |= rendered

    if compatible:
        summary_lines.append("== Compatible (input longer than known format) ==\n")
        summary_lines.append("These may indicate framing/padding.\n\n")
        rendered, diag, chunks, rows = _render_candidates(
            binary_string, compatible, slice_mode=slice_mode, show_parity_failures=show_parity_failures
        )
        diagnostics_rendered.extend(diag)
        summary_lines.extend(chunks)
        table_rows.extend(rows)
        rendered_any |= rendered

    if not rendered_any:
        summary_lines.append(
            "No formats passed parity in strict mode.\n"
            "Tip: Enable 'Parity diagnostics' to inspect candidates.\n"
        )

    diagnostics_context["rendered"].extend(diagnostics_rendered)
    diagnostics_text = build_diagnostics_report(diagnostics_context)
    parity_results, primary_format, offset = _choose_primary_parity(diagnostics_rendered)
    parity_ok = _parity_all_ok(parity_results) if parity_results else None

    return AnalysisResult(
        success=True,
        error=None,
        binary=binary_string,
        summary_text="".join(summary_lines),
        diagnostics_text=diagnostics_text,
        table_rows=table_rows,
        parity_results=parity_results,
        primary_format=primary_format,
        offset=offset,
        input_meta=input_meta,
        exact_matches=diagnostics_context["exact_matches"],
        compatible_matches=diagnostics_context["compatible_matches"],
        slice_mode=slice_mode,
        rendered=diagnostics_rendered,
        parity_ok=parity_ok,
    )


__all__ = ["TableRow", "AnalysisResult", "analyze_input"]
