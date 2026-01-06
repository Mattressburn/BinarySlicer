from binaryslicer.controller import Controller
from binaryslicer.formats import normalize_format_entry
from binaryslicer.history import HistoryBuffer


def test_list_formats_returns_ids_and_display_names():
    controller = Controller()

    formats = controller.list_formats()

    assert any(fmt_id == "H10301 - 26-bit" and name == "H10301 - 26-bit" for fmt_id, name, _ in formats)
    names = [name for _, name, _ in formats]
    assert names == sorted(names, key=str.lower)


def test_analyze_input_respects_forced_format_and_matches_auto_when_same():
    fmt_a = normalize_format_entry(
        {
            "name": "TestFrameA",
            "bit_length": 8,
            "fields": [
                {"name": "Prefix", "start": 0, "end": 3},
                {"name": "Payload", "start": 4, "end": 7},
            ],
        }
    )
    fmt_b = normalize_format_entry(
        {
            "name": "TestFrameB",
            "bit_length": 4,
            "fields": [
                {"name": "Nibble", "start": 0, "end": 3},
            ],
        }
    )

    class DummyRepo:
        def __init__(self, formats):
            self.formats_by_id = {fmt.format_id: fmt for fmt in formats}
            self.formats = {fmt.name: fmt for fmt in formats}

    repo = DummyRepo([fmt_a, fmt_b])
    controller = Controller(repo)
    payload = "10101100"

    auto = controller.analyze_input(payload, slice_mode="left")
    forced = controller.analyze_input(payload, slice_mode="left", forced_format_id=fmt_a.format_id)
    invalid = controller.analyze_input(payload, slice_mode="left", forced_format_id="missing-format")

    def values_for(result, format_name):
        return {(row.field, row.value) for row in result.table_rows if row.format_name.startswith(format_name)}

    assert auto.best_format_id == fmt_a.format_id
    assert forced.best_format_id == fmt_a.format_id
    assert forced.selection_source == "forced"
    assert values_for(forced, fmt_a.name) == values_for(auto, fmt_a.name)
    assert invalid.best_format_id == fmt_a.format_id
    assert invalid.status_message
    assert invalid.selection_source == "exact"


def test_history_buffer_caps_entries():
    history = HistoryBuffer(max_items=10)

    for i in range(12):
        bits = f"{i:08b}"
        history.add(
            raw_bits=bits,
            bit_length=len(bits),
            format_name="TestFrame",
            format_id="TestFrame",
            forced_format_id=None,
            reverse_bits=bool(i % 2),
            parity_ok=True,
        )

    assert len(history.entries) == 10
    assert history.entries[0].raw_bits == f"{11:08b}"
    assert history.entries[-1].raw_bits == f"{2:08b}"
