from binaryslicer.formats import bits_to_int, extract_fields, normalize_format_entry, verify_parity


def make_format():
    doc = {
        "name": "Test 8-bit",
        "bit_length": 8,
        "fields": [
            {"name": "Parity", "start": 0, "end": 0},
            {"name": "Data", "start": 1, "end": 7},
        ],
        "parity": [
            {"type": "even", "ranges": [{"start": 1, "end": 7}]},
        ],
    }
    return normalize_format_entry(doc)


def test_bits_to_int():
    assert bits_to_int("1010") == 10
    assert bits_to_int("") == 0


def test_extract_fields_returns_ranges():
    fmt = make_format()
    fields = extract_fields("01100101", fmt)
    assert fields["Parity"]["bits"] == "0"
    assert fields["Data"]["bits"] == "1100101"
    assert fields["Data"]["range"] == (1, 7)


def test_verify_parity_calculates_expected_bit():
    fmt = make_format()
    parity = verify_parity("01100101", fmt)
    assert len(parity) == 1
    entry = parity[0]
    assert entry["coverage"] == (1, 7)
    # 1100101 contains four ones, so even parity requires a 0 bit
    assert entry["expected"] == 0
