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
    prepare_bits_for_format,
    verify_parity,
)

# Canonical user-facing label for the default 26-bit Wiegand profile.
WIEGAND26_DISPLAY = "Standard Wiegand 26 (H10301)"
WIEGAND26_ALIAS_KEYS = {
    "h10301 - 26-bit",
    "h10301",
    "standard wiegand 26",
    "standard wiegand 26 (h10301)",
    "wiegand-26 (h10301)",
    "wiegand-26",
    "standard 26-bit wiegand",
}


@dataclass
class TableRow:
    """Row for the primary results table."""

    field: str
    range: str
    value: str
    hex: str
    format_name: str
    bits: str


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
    best_format: Optional[str] = None
    best_format_id: Optional[str] = None
    selection_source: Optional[str] = None
    slice_mode: Optional[str] = None
    bit_length: int = 0
    forced_format_id: Optional[str] = None
    status_message: Optional[str] = None


class Controller:
    """Encapsulates BinarySlicer parsing and diagnostics."""

    def __init__(self, repo: Optional[FormatRepository] = None) -> None:
        self.repo = repo or FormatRepository()

    def analyze_input(
        self,
        raw_input: str,
        *,
        slice_mode: str = "auto",
        show_parity_failures: bool = False,
        reverse_bits: bool = False,
        forced_format_id: Optional[str] = None,
    ) -> AnalysisResult:
        """Normalize input, select formats, and render results."""

        binary_string, error, input_meta = process_input(raw_input)
        input_meta.update(
            {
                "reverse_bits": reverse_bits,
                "bit_order": "reversed" if reverse_bits else "normal",
            }
        )
        result = AnalysisResult(
            error=error, input_meta=input_meta, slice_mode=slice_mode, forced_format_id=forced_format_id
        )
        if error or not binary_string:
            return result

        forced_candidate: Optional[Tuple[str, NormalizedFormat]] = None
        if forced_format_id:
            forced_candidate = self._resolve_forced_format(forced_format_id)
            if not forced_candidate:
                result.status_message = f"Format '{forced_format_id}' is not available. Falling back to auto-detect."
                forced_format_id = None
            else:
                result.forced_format_id = forced_candidate[0]

        working_bits = binary_string[::-1] if reverse_bits else binary_string
        input_meta["normalized_bits"] = binary_string
        input_meta["working_bits"] = working_bits

        result.bit_length = len(working_bits)
        exact: List[Tuple[str, NormalizedFormat]] = []
        compatible: List[Tuple[str, NormalizedFormat]] = []
        if forced_candidate:
            exact = [forced_candidate]
        else:
            exact, compatible = self._detect_formats(working_bits)

        # Exact vs Compatible:
        # - Exact: bit-length matches or a canonical zero-offset Wiegand-26 window with clean parity,
        #   tolerating only benign trailing zero padding.
        # - Compatible: longer inputs requiring non-zero offsets or framing to find a passing window.
        promoted: List[Tuple[str, NormalizedFormat]] = []
        remaining: List[Tuple[str, NormalizedFormat]] = []
        for fmt_id, fmt in compatible:
            candidates = find_best_offsets(working_bits, fmt, step=1, top_n=1)
            if candidates and self._should_promote_w26_exact(working_bits, fmt, candidates[0]):
                promoted.append((fmt_id, fmt))
            else:
                remaining.append((fmt_id, fmt))
        if promoted:
            exact.extend(promoted)
        compatible = remaining

        summary_lines: List[str] = []
        selection_label = "Auto-detect"
        if forced_candidate:
            selection_label = f"Forced format: {forced_candidate[1].name}"
        elif result.status_message:
            selection_label = f"Auto-detect (fallback)"

        summary_lines.append(f"Selection: {selection_label}\n")
        summary_lines.append(f"Bit order: {input_meta['bit_order']}\n")
        if reverse_bits:
            summary_lines.append(f"Raw bits ({len(binary_string)} bits):\n{format_binary_groups(binary_string)}\n\n")
            summary_lines.append(
                f"Working bits ({len(working_bits)} bits):\n{format_binary_groups(working_bits)}\n\n"
            )
        else:
            summary_lines.append(f"Binary ({len(working_bits)} bits):\n{format_binary_groups(working_bits)}\n\n")

        diagnostics_context: Dict = {
            "input": input_meta,
            "exact_matches": [self._alias_format_name(fmt.name, fmt.format_id) for _, fmt in exact],
            "compatible_matches": [self._alias_format_name(fmt.name, fmt.format_id) for _, fmt in compatible],
            "rendered": [],
            "auto_candidates": [],
            "slice_mode": slice_mode,
            "winner": {},
            "bit_order": input_meta["bit_order"],
            "reverse_bits": reverse_bits,
        }

        if not exact and not compatible:
            summary_lines.append("No matching formats found.\n")
            result.summary = "".join(summary_lines)
            result.diagnostics_text = build_diagnostics_report(diagnostics_context)
            return result

        diag_entries: List[Dict] = []
        rendered_entries: List[Dict] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}
        rendered_any = False

        if exact:
            summary_lines.append("== Exact bit-length matches ==\n")
            rendered, diag_list, chunks, csv_rows, table_rows, parity_map = self._render_candidates(
                working_bits,
                exact,
                slice_mode,
                show_parity_failures,
                match_type="forced" if forced_candidate else "exact",
            )
            if rendered:
                rendered_entries.extend([entry for entry in diag_list if (entry.get("meta") or {}).get("rendered")])
                summary_lines.extend(chunks)
                result.csv_rows.extend(csv_rows)
                result.table_rows.extend(table_rows)
                rendered_any = True
            diag_entries.extend(diag_list)
            parity_rows_map.update(parity_map)

        if compatible:
            summary_lines.append("== Compatible (input longer than known format) ==\n")
            summary_lines.append("These may indicate framing/padding.\n\n")
            rendered, diag_list, chunks, csv_rows, table_rows, parity_map = self._render_candidates(
                working_bits, compatible, slice_mode, show_parity_failures, match_type="compatible"
            )
            if rendered:
                rendered_entries.extend([entry for entry in diag_list if (entry.get("meta") or {}).get("rendered")])
                summary_lines.extend(chunks)
                result.csv_rows.extend(csv_rows)
                result.table_rows.extend(table_rows)
                rendered_any = True
            diag_entries.extend(diag_list)
            parity_rows_map.update(parity_map)

        if not rendered_any:
            summary_lines.append(
                "No formats passed parity in strict mode.\n"
                "Tip: enable parity diagnostics to inspect gated failures.\n"
            )

        best_entry, selection_source = self._pick_best_entry(diag_entries)
        if best_entry:
            parity = best_entry.get("parity") or []
            stats = parity_score(parity)
            result.parity_stats = stats
            result.parity_ok = stats["gated_fail"] == 0 if stats["gating_present"] else None
            result.best_offset = best_entry.get("meta", {}).get("offset")
            result.best_format = best_entry.get("format")
            result.best_format_id = best_entry.get("format_id")
            result.selection_source = "forced" if forced_candidate else selection_source
            if forced_candidate:
                result.best_format = forced_candidate[1].name
                result.best_format_id = forced_candidate[0]
            parity_rows = parity_rows_map.get(best_entry["name"], [])
            if not show_parity_failures:
                parity_rows = [row for row in parity_rows if row.ok is False]
            result.parity_rows = parity_rows or parity_rows_map.get(best_entry["name"], [])

            diagnostics_context["winner"] = {
                "name": best_entry.get("format") or best_entry.get("name"),
                "match_type": result.selection_source,
                "parity_stats": stats,
            }

        diagnostics_context["rendered"].extend(rendered_entries)
        result.formats_rendered = [entry.get("name") for entry in rendered_entries if entry.get("name")]
        result.summary = "".join(summary_lines)
        result.diagnostics_text = build_diagnostics_report(diagnostics_context)

        return result

    def list_formats(self) -> List[Tuple[str, str, int]]:
        """Return available formats as (id, display_name, bit_length), sorted by display name."""

        entries: List[Tuple[str, str, int]] = []
        for fmt_id, fmt in self.repo.formats_by_id.items():
            entries.append((fmt_id, fmt.name, fmt.bit_length))
        return sorted(entries, key=lambda x: x[1].lower())

    def _resolve_forced_format(self, fmt_id: str) -> Optional[Tuple[str, NormalizedFormat]]:
        for candidate_id, fmt in self.repo.formats_by_id.items():
            if candidate_id == fmt_id or candidate_id.lower() == fmt_id.lower():
                return candidate_id, fmt
            if fmt.name.lower() == fmt_id.lower():
                return candidate_id, fmt
        return None

    def _detect_formats(self, binary_string: str) -> Tuple[List[Tuple[str, NormalizedFormat]], List[Tuple[str, NormalizedFormat]]]:
        exact: List[Tuple[str, NormalizedFormat]] = []
        compatible: List[Tuple[str, NormalizedFormat]] = []
        input_len = len(binary_string)

        for fmt_id, fmt in self.repo.formats_by_id.items():
            length = fmt.bit_length

            # Check if format has used_bits specified (for embedded formats in larger payloads)
            # If used_bits matches bit_length and input >= used_bits, treat as exact match
            if fmt.used_bits is not None and fmt.used_bits == length:
                if input_len >= fmt.used_bits:
                    exact.append((fmt_id, fmt))
                continue

            if input_len == length:
                exact.append((fmt_id, fmt))
            elif input_len > length:
                compatible.append((fmt_id, fmt))

        return exact, compatible

    def _render_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        slice_mode: Optional[str],
        show_parity_failures: bool,
        *,
        match_type: Optional[str] = None,
    ) -> Tuple[bool, List[Dict], List[str], List[Dict], List[TableRow], Dict[str, List[ParityRow]]]:
        rendered = False
        diagnostics: List[Dict] = []
        all_entries: List[Dict] = []
        summaries: List[str] = []
        csv_rows: List[Dict] = []
        table_rows: List[TableRow] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}

        if slice_mode == "auto":
            return self._render_auto_candidates(
                binary_string, candidates, show_parity_failures, match_type=match_type
            )

        for fmt_id, fmt in candidates:
            # For formats with used_bits defined, extract the used region first
            if fmt.used_bits is not None:
                use_bits = prepare_bits_for_format(binary_string, fmt)
                base_name = fmt.name + " (aligned)"
            else:
                use_bits, base_name = self._slice_bits(binary_string, fmt.bit_length, slice_mode, fmt.name)
            display_name = self._alias_format_name(base_name, fmt.format_id)
            summary_block, diag_entry, rows, csv_data, parity_rows = self._render_format(
                use_bits,
                display_name,
                fmt,
                {"mode": slice_mode, "match": match_type},
                format_name=self._alias_format_name(fmt.name, fmt.format_id),
            )
            meta = dict(diag_entry.get("meta") or {})
            meta.update({"mode": slice_mode, "match": match_type})
            diag_entry["meta"] = meta
            diag_entry["format_id"] = fmt_id
            parity_rows_map[diag_entry["name"]] = parity_rows
            all_entries.append(diag_entry)

            stats = diag_entry.get("parity_stats") or {}
            should_render = show_parity_failures or match_type in {"exact", "forced"} or stats.get("gated_fail", 0) == 0
            diag_entry["meta"]["rendered"] = bool(should_render)
            if not should_render:
                continue

            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            csv_rows.extend(csv_data)
            table_rows.extend(rows)
            rendered = True

        return rendered, all_entries, summaries, csv_rows, table_rows, parity_rows_map

    def _render_auto_candidates(
        self,
        binary_string: str,
        candidates: Sequence[Tuple[str, NormalizedFormat]],
        show_parity_failures: bool,
        *,
        match_type: Optional[str] = None,
    ) -> Tuple[bool, List[Dict], List[str], List[Dict], List[TableRow], Dict[str, List[ParityRow]]]:
        rendered = False
        diagnostics: List[Dict] = []
        all_entries: List[Dict] = []
        summaries: List[str] = []
        csv_rows: List[Dict] = []
        table_rows: List[TableRow] = []
        parity_rows_map: Dict[str, List[ParityRow]] = {}
        all_results: List[Dict] = []

        for fmt_id, fmt in candidates:
            # For formats with used_bits defined, use the aligned region directly (no offset search)
            if fmt.used_bits is not None:
                aligned_bits = prepare_bits_for_format(binary_string, fmt)
                parity_results = verify_parity(aligned_bits, fmt)
                stats = parity_score(parity_results)
                all_results.append({
                    "name": fmt.name,
                    "fmt": fmt,
                    "candidate": {
                        "offset": 0,
                        "bits": aligned_bits,
                        "parity": parity_results,
                        "stats": stats,
                        "score_key": stats["score_tuple"] + (0,),
                        "aligned": True,
                    },
                    "format_id": fmt_id,
                })
            else:
                best = find_best_offsets(binary_string, fmt, step=1, top_n=3)
                for candidate in best:
                    all_results.append({"name": fmt.name, "fmt": fmt, "candidate": candidate, "format_id": fmt_id})

        if not all_results:
            return False, diagnostics, summaries, csv_rows, table_rows, parity_rows_map

        all_results.sort(key=lambda c: c["candidate"]["score_key"], reverse=True)
        limit = max(3, min(len(all_results), 10))
        for entry in all_results[:limit]:
            cand = entry["candidate"]
            stats = cand["stats"]
            parity = cand["parity"]
            base_name = self._alias_format_name(entry["name"], entry["format_id"])
            # Show different label for aligned vs auto-offset formats
            if cand.get("aligned"):
                display_name = (
                    f"{base_name} (MSB aligned, "
                    f"pass {stats['total_pass']}/{len(parity)}, gated_fail={stats['gated_fail']})"
                )
            else:
                display_name = (
                    f"{base_name} (auto offset +{cand['offset']}, "
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
                    "match": match_type,
                },
                format_name=base_name,
            )
            meta = dict(diag_entry.get("meta") or {})
            meta.update({"mode": "auto", "offset": cand["offset"], "match": match_type})
            diag_entry["meta"] = meta
            diag_entry["format_id"] = entry["format_id"]
            parity_rows_map[diag_entry["name"]] = parity_rows
            all_entries.append(diag_entry)

            should_render = show_parity_failures or stats["gated_fail"] == 0
            diag_entry["meta"]["rendered"] = bool(should_render)
            if not should_render:
                continue

            summaries.append(summary_block)
            diagnostics.append(diag_entry)
            csv_rows.extend(csv_data)
            table_rows.extend(rows)
            rendered = True

        return rendered, all_entries, summaries, csv_rows, table_rows, parity_rows_map

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

    @staticmethod
    def _is_wiegand_26(fmt: NormalizedFormat) -> bool:
        name = (fmt.name or "").lower()
        fmt_id = (fmt.format_id or "").lower()
        return fmt.bit_length == 26 and ("wiegand" in name or "h10301" in name or "h10301" in fmt_id)

    @staticmethod
    def _alias_format_name(name: str, format_id: Optional[str]) -> str:
        key_name = (name or "").lower()
        key_id = (format_id or "").lower()
        if key_name in WIEGAND26_ALIAS_KEYS or key_id in WIEGAND26_ALIAS_KEYS:
            return WIEGAND26_DISPLAY
        return name

    def _should_promote_w26_exact(self, bits: str, fmt: NormalizedFormat, candidate: Mapping) -> bool:
        if not self._is_wiegand_26(fmt):
            return False
        if candidate.get("offset") != 0:
            return False
        stats = candidate.get("stats") or {}
        if stats.get("gated_fail", 1) != 0:
            return False
        if len(bits) > fmt.bit_length and any(ch == "1" for ch in bits[fmt.bit_length :]):
            return False
        return True

    def _render_format(
        self,
        binary_string: str,
        name: str,
        fmt: NormalizedFormat,
        meta: Optional[Mapping] = None,
        *,
        format_name: Optional[str] = None,
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
            view = str(info.get("view") or "")
            if view.startswith("ansi_bcd5") or view in ("ansi_bcd5", "ansi_bcd"):
                display_value = str(info.get("display") or info["int"])
            else:
                display_value = str(info["int"])
            summary_lines.append(f"  {field:14}: {display_value} (hex {info['hex']}), bits[{info['len']}]={info['bits']}\n")
            table_rows.append(
                TableRow(
                    field=field,
                    range=range_text,
                    value=display_value,
                    hex=info["hex"],
                    format_name=name,
                    bits=info["bits"],
                )
            )
            csv_rows.append(
                {
                    "Format": name,
                    "Field": field,
                    "Value": display_value,
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
            "format": format_name or name,
            "format_id": fmt.format_id,
            "bit_length": len(binary_string),
            "parity": parity,
            "parity_stats": parity_score(parity or []),
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
    def _pick_best_entry(entries: Sequence[Mapping]) -> Tuple[Optional[Mapping], Optional[str]]:
        if not entries:
            return None, None

        def score(entry: Mapping) -> Tuple:
            stats = entry.get("parity_stats") or {}
            return (stats.get("score_tuple") or (False, 0, 0, 0, 0), entry.get("bit_length") or 0)

        def match(entry: Mapping) -> Optional[str]:
            return (entry.get("meta") or {}).get("match")

        forced_entries = [entry for entry in entries if match(entry) == "forced"]
        exact_entries = [entry for entry in entries if match(entry) == "exact"]
        compatible_entries = [entry for entry in entries if match(entry) == "compatible"]
        pool = forced_entries or exact_entries or compatible_entries
        source = (
            "forced"
            if forced_entries
            else "exact"
            if exact_entries
            else "compatible"
            if compatible_entries
            else None
        )

        gated_ok = [
            entry
            for entry in pool
            if (entry.get("parity_stats") or {}).get("gating_present")
            and (entry.get("parity_stats") or {}).get("gated_fail") == 0
        ]
        if gated_ok:
            pool = gated_ok

        return (max(pool, key=score), source) if pool else (None, None)


__all__ = ["Controller", "AnalysisResult", "TableRow", "ParityRow"]
