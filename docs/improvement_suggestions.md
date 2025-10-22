# Improvement Opportunities

## Format management

* `FormatRepository` loads documents and normalizes entries without validating field and parity ranges, so malformed JSON can slip through and cause runtime issues later in the UI. Adding schema validation (for example with `jsonschema`) before `normalize_format_entry` would catch negative ranges or overlaps early. 【F:binaryslicer/formats.py†L20-L78】
* `_detect_formats` only compares raw bit lengths, which means payloads that need leading/trailing padding or have ambiguous lengths cannot be surfaced automatically. Extending this logic to scan for sliding windows or to score partial matches would make the decoder more forgiving. 【F:binaryslicer/ui.py†L678-L704】
* Exported format packs do not carry provenance (e.g., author, source URL). Extending the JSON schema with optional metadata fields would help operators audit custom entries while keeping backward compatibility.

## UI and UX

* `on_calculate` immediately surfaces errors via modal dialogs but does not preserve the prior analysis in the main text widget, so users lose context when pasting a bad payload. Keeping the previous output visible and showing non-blocking inline error messaging would improve the troubleshooting flow. 【F:binaryslicer/ui.py†L640-L668】
* The parity visualizer shows only expected bits; enhancing `_render_format` or the canvas drawing routine to annotate which ranges failed parity would make the diagnostic toggle more actionable. 【F:binaryslicer/ui.py†L705-L722】
* Adding keyboard shortcuts for common menu items (import/export formats, toggle theme) would make heavy use more efficient; the current `_build_menu` configuration has no accelerators defined. 【F:binaryslicer/ui.py†L188-L207】

## Testing

* The current tests exercise a single synthetic 8-bit format; real-world regressions (e.g., parity coverage mistakes) are not captured. Parameterizing `test_formats` with the bundled JSON definitions would guard against future format pack updates. 【F:tests/test_formats.py†L1-L33】
* There are no UI smoke tests to ensure the Tkinter menu wiring stays valid. A lightweight test that instantiates `App` with a `tk.Tk()` stub and inspects menu labels would catch accidental regressions in `_build_menu`. 【F:binaryslicer/ui.py†L112-L207】
