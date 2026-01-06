import json
from pathlib import Path

from binaryslicer.controller import Controller
from binaryslicer.formats import FormatRepository


FASC_SAMPLE_200BIT = (
    "10111010110001101110111000101111110011011010111100001000111000101011011010110000011011010110010001111001101011110101101011111000011111110011111001011100001000001111111111110001111110101001001101001000"
)


def test_exact_length_prioritized_over_compatible_with_parity_failures():
    repo = FormatRepository()
    # Ensure the full bundled formats (including FASC-N) are available in the temp config.
    repo.merge(json.loads(Path("config/formats.json").read_text()))
    controller = Controller(repo)

    result = controller.analyze_input(FASC_SAMPLE_200BIT)

    assert result.best_format == "FASC-N (CHUID) - 200-bit"
    assert result.selection_source == "exact"
    assert result.parity_stats.get("gating_present") is True
    assert result.parity_stats.get("gated_fail") == 0
    assert result.parity_ok is True
    assert "FASC-N (CHUID) - 200-bit" in result.summary
    assert "exact-length priority" in result.diagnostics_text
    assert "gated parity: fail=0" in result.diagnostics_text
