from binaryslicer.controller import Controller
from binaryslicer.decoder import process_input
from binaryslicer.formats import FormatRepository
from tests.test_selection_priority import FASC_SAMPLE_200BIT


W26_HEX = "841EEE40"


def _get_w26(repo: FormatRepository):
    for fmt_id, fmt in repo.formats_by_id.items():
        name = (fmt.name or "").lower()
        if fmt.bit_length == 26 and ("wiegand" in name or "h10301" in name):
            return fmt_id, fmt
    raise AssertionError("Wiegand 26 format not found")


def _w26_only_repo() -> FormatRepository:
    base = FormatRepository()
    fmt_id, fmt = _get_w26(base)

    class SingleRepo:
        def __init__(self, fmt_id, fmt):
            self.formats_by_id = {fmt_id: fmt}
            self.formats = {fmt.name: fmt}

    return SingleRepo(fmt_id, fmt)  # type: ignore[return-value]


def test_wiegand26_padded_hex_promoted_to_exact():
    controller = Controller(FormatRepository())

    result = controller.analyze_input(W26_HEX)

    assert result.best_format == "Standard Wiegand 26 (H10301)"
    assert result.selection_source == "exact"
    assert result.best_offset == 0
    assert result.parity_ok is True

    rows = [row for row in result.table_rows if "Standard Wiegand 26" in row.format_name]
    assert rows, "Expected Wiegand 26 rows to be rendered"
    values = {row.field: int(row.value) for row in rows}
    assert values["Facility Code"] == 8
    assert values["Card Number"] == 15836


def test_wiegand26_shifted_offset_stays_compatible():
    binary, _, _ = process_input(W26_HEX)
    assert binary is not None
    shifted = "00" + binary  # introduce padding so the canonical window starts at offset 2

    controller = Controller(_w26_only_repo())
    result = controller.analyze_input(shifted)

    assert result.selection_source == "compatible"
    assert result.best_offset is not None and result.best_offset != 0
    assert result.best_format in {"Standard Wiegand 26 (H10301)", "H10301 - 26-bit"}


def test_other_format_remains_exact():
    controller = Controller(FormatRepository())

    result = controller.analyze_input(FASC_SAMPLE_200BIT)

    assert result.selection_source == "exact"
    assert result.parity_ok is True
    assert result.best_format and "FASC" in result.best_format
