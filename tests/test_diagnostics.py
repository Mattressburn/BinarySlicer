from binaryslicer.diagnostics import build_diagnostics_report, parity_result_color


def test_build_diagnostics_report_includes_sections():
    context = {
        "input": {
            "raw_length": 10,
            "cleaned_length": 8,
            "normalized_length": 8,
            "input_type": "binary",
            "cleaned": "10101010",
        },
        "exact_matches": ["ExactOne"],
        "compatible_matches": ["CompatA", "CompatB"],
        "slice_mode": "auto",
        "rendered": [
            {
                "name": "ExactOne",
                "bit_length": 8,
                "parity": [
                    {
                        "label": "Even Parity",
                        "type": "even",
                        "coverage": (0, 3),
                        "expected": 1,
                        "actual": 1,
                        "ok": True,
                        "parity_bit": 3,
                        "gate": True,
                    },
                    {
                        "label": "Odd Parity",
                        "type": "odd",
                        "coverage": (4, 7),
                        "expected": 0,
                        "actual": 1,
                        "ok": False,
                        "parity_bit": 7,
                        "gate": False,
                    },
                ],
                "meta": {"mode": "auto", "offset": 0},
            }
        ],
    }

    report = build_diagnostics_report(context)

    assert "raw length=10" in report
    assert "Exact bit-length matches: ExactOne" in report
    assert "Compatible matches: CompatA, CompatB" in report
    assert "Totals: pass=1, fail=1" in report
    assert "Odd Parity 4–7: fail" in report


def test_parity_result_color_mapping():
    theme = {"accent": "#111", "ok": "#0f0", "warn": "#ff0", "error": "#f00"}

    assert parity_result_color({"ok": True, "gate": True}, theme, True) == "#0f0"
    assert parity_result_color({"ok": False, "gate": True}, theme, True) == "#f00"
    assert parity_result_color({"ok": False, "gate": False}, theme, True) == "#ff0"
    assert parity_result_color({"ok": None, "gate": True}, theme, True) == "#ff0"
    # When diagnostics are hidden, fall back to accent color
    assert parity_result_color({"ok": False, "gate": True}, theme, False) == "#111"
