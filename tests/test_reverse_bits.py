from binaryslicer.controller import Controller
from binaryslicer.formats import normalize_format_entry


def _make_repo():
    fmt = normalize_format_entry(
        {
            "name": "TestFrame",
            "bit_length": 8,
            "fields": [
                {"name": "Prefix", "start": 0, "end": 3},
                {"name": "Payload", "start": 4, "end": 7},
            ],
        }
    )

    class DummyRepo:
        def __init__(self, format_entry):
            self.formats = {"TestFrame": format_entry}
            self.formats_by_id = {format_entry.format_id: format_entry}

    return DummyRepo(fmt)


def test_reverse_bits_switches_working_slice():
    controller = Controller(_make_repo())
    payload = "11010011"

    normal = controller.analyze_input(payload, reverse_bits=False, slice_mode="left")
    reversed_result = controller.analyze_input(payload, reverse_bits=True, slice_mode="left")

    normal_fields = {row.field: int(row.value) for row in normal.table_rows}
    reversed_fields = {row.field: int(row.value) for row in reversed_result.table_rows}

    assert normal_fields == {"Prefix": 13, "Payload": 3}
    assert reversed_fields == {"Prefix": 12, "Payload": 11}
    assert reversed_result.input_meta["reverse_bits"] is True
    assert reversed_result.input_meta["bit_order"] == "reversed"
    assert reversed_result.input_meta["working_bits"] == payload[::-1]
    assert reversed_result.input_meta["normalized_bits"] == payload


def test_normal_order_matches_original_bits():
    controller = Controller(_make_repo())
    payload = "01011100"

    result = controller.analyze_input(payload)

    values = {row.field: int(row.value) for row in result.table_rows}
    assert values == {"Prefix": 5, "Payload": 12}
    assert result.best_format == "TestFrame"
    assert result.input_meta["reverse_bits"] is False
    assert result.input_meta["bit_order"] == "normal"
    assert result.input_meta["working_bits"] == payload
