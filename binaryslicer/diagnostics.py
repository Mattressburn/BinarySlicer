"""Diagnostics helpers for BinarySlicer."""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping

from .formats import parity_score


def _format_input_section(meta: Mapping) -> str:
    if not meta:
        return "Input normalization: unavailable\n"
    raw_len = meta.get("raw_length", 0)
    cleaned_len = meta.get("cleaned_length", 0)
    normalized_len = meta.get("normalized_length", 0)
    input_type = meta.get("input_type", "unknown")
    return (
        "Input normalization:\n"
        f"  raw length={raw_len}, cleaned length={cleaned_len}, normalized length={normalized_len}\n"
        f"  detected type={input_type}, cleaned='{meta.get('cleaned', '')}'\n\n"
    )


def _format_selection_section(context: Mapping) -> str:
    exact = context.get("exact_matches") or []
    compatible = context.get("compatible_matches") or []
    slice_mode = context.get("slice_mode")
    winner = context.get("winner") or {}
    parity_stats = winner.get("parity_stats") or {}
    gating_present = parity_stats.get("gating_present", False)
    gated_fail = parity_stats.get("gated_fail", 0)
    gated_pass = parity_stats.get("gated_pass", 0)
    lines = ["Format selection:\n"]
    lines.append(f"  Exact bit-length matches: {', '.join(exact) if exact else 'none'}\n")
    lines.append(f"  Compatible matches: {', '.join(compatible) if compatible else 'none'}\n")
    if slice_mode:
        lines.append(f"  Compatible slicing mode: {slice_mode}\n")
    if winner:
        match_type = winner.get("match_type") or "candidates"
        reason = "exact-length priority" if match_type == "exact" else "compatible fallback"
        if gating_present:
            parity_note = f"gated parity: fail={gated_fail}, pass={gated_pass}"
        else:
            parity_note = "parity: no gated checks"
        lines.append(f"  Winner: {winner.get('name','(unknown)')} ({reason}; {parity_note})\n")
    return "".join(lines) + "\n"


def _format_auto_candidates(rendered: Iterable[Mapping]) -> str:
    lines: List[str] = []
    for entry in rendered:
        meta = entry.get("meta") or {}
        top = meta.get("top_candidates") or []
        if not top:
            continue
        lines.append(f"Auto offset search for {entry.get('name','format')}:\n")
        for cand in top:
            stats = cand["candidate"]["stats"]
            parity_count = len(cand["candidate"]["parity"])
            lines.append(
                f"  offset +{cand['candidate']['offset']}: "
                f"gated_pass={stats['gated_pass']}, gated_fail={stats['gated_fail']}, "
                f"total_pass={stats['total_pass']}/{parity_count}\n"
            )
        lines.append("\n")
    return "".join(lines)


def _format_parity_detail(parity: List[Dict]) -> tuple[str, Dict[str, int]]:
    if not parity:
        return "  (no parity rules)\n", {"total": 0, "pass": 0, "fail": 0, "gated_fail": 0, "gated_pass": 0}
    stats = parity_score(parity)
    lines: List[str] = []
    for item in parity:
        coverage = f"{item['coverage'][0]}–{item['coverage'][1]}"
        status = "pass" if item.get("ok") else "fail" if item.get("ok") is False else "not evaluated"
        expected = item.get("expected")
        actual = item.get("actual")
        parity_bit = item.get("parity_bit")
        note = "advisory" if not item.get("gate", True) else "gated"
        parity_bit_str = f", parity_bit={parity_bit}" if parity_bit is not None else ""
        lines.append(
            f"  {item.get('label', item.get('type','parity'))} {coverage}: {status}"
            f" (expected {expected}, actual {actual}{parity_bit_str}, {note})\n"
        )
    summary = (
        f"  Totals: pass={stats['total_pass']}, fail={stats['total_fail']}, "
        f"gated_pass={stats['gated_pass']}, gated_fail={stats['gated_fail']}\n"
    )
    lines.append(summary)
    return "".join(lines), {
        "total": len(parity),
        "pass": stats["total_pass"],
        "fail": stats["total_fail"],
        "gated_fail": stats["gated_fail"],
        "gated_pass": stats["gated_pass"],
    }


def build_diagnostics_report(context: Mapping) -> str:
    """Render a textual diagnostics report."""
    input_section = _format_input_section(context.get("input") or {})
    selection = _format_selection_section(context)
    auto = _format_auto_candidates(context.get("rendered") or [])

    parity_lines: List[str] = ["Parity checks:\n"]
    rendered = context.get("rendered") or []
    if not rendered:
        parity_lines.append("  No formats rendered.\n")
    for entry in rendered:
        parity_lines.append(f"- {entry.get('name','format')} ({entry.get('bit_length','?')} bits)\n")
        detail, _ = _format_parity_detail(entry.get("parity") or [])
        parity_lines.append(detail)
    parity_section = "".join(parity_lines)

    return input_section + selection + auto + parity_section


def parity_result_color(result: Mapping, theme: Mapping[str, str], show_diagnostic: bool) -> str:
    """Map a parity result to a theme-aware color."""
    base = theme.get("accent", "#0399CC")
    if not show_diagnostic:
        return base
    ok_color = theme.get("ok", base)
    warn_color = theme.get("warn", theme.get("accent2", base))
    error_color = theme.get("error", theme.get("accent2", base))

    if result.get("ok") is True:
        return ok_color
    if result.get("ok") is False:
        return error_color if result.get("gate", True) else warn_color
    # Not evaluated or missing parity bit
    return warn_color


__all__ = ["build_diagnostics_report", "parity_result_color"]
