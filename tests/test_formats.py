import json

from binaryslicer.formats import (
    bits_to_int,
    extract_fields,
    normalize_format_entry,
    parity_even_bit_needed,
    parity_odd_bit_needed,
    parity_score,
    verify_parity,
)


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


FASC_VECTOR = (
    "11010100001001111101100011011000001000010000101000101101000111001001010011111001010001011000001101101000010110000011001100101100000100010011101011100111001010001000010000100111110110001100011111110110"
)


def load_format(name: str):
    with open("config/formats.json", "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    entry = next(fmt for fmt in doc["formats"] if fmt.get("name") == name)
    return normalize_format_entry(entry)


def fill_parity_bit(bits: list[str], start: int, end: int, parity_type: str, parity_bit_index: int) -> None:
    data = "".join(bits[start : end + 1])
    func = parity_even_bit_needed if parity_type == "even" else parity_odd_bit_needed
    bits[parity_bit_index] = str(func(data))


def test_fasc_parity_accepts_known_vector():
    fmt = load_format("FASC-N (CHUID) - 200-bit")
    parity = verify_parity(FASC_VECTOR, fmt)
    stats = parity_score(parity)
    assert stats["gated_fail"] == 0
    assert stats["total_fail"] == 0
    assert len(parity) == 40
    assert any(entry["configured_type"] != entry["type"] for entry in parity) is True


def test_parity_position_sets_index():
    bits = "11010" "10000"  # two valid odd-parity characters
    fmt_msb = normalize_format_entry(
        {
            "name": "Two chars msb",
            "bit_length": 10,
            "fields": [],
            "parity": [
                {
                    "type": "odd",
                    "per_character": True,
                    "character_width": 5,
                    "parity_position": "msb",
                    "start": 0,
                    "end": 9,
                }
            ],
        }
    )
    fmt_lsb = normalize_format_entry(
        {
            "name": "Two chars lsb",
            "bit_length": 10,
            "fields": [],
            "parity": [
                {
                    "type": "odd",
                    "per_character": True,
                    "character_width": 5,
                    "parity_position": "lsb",
                    "start": 0,
                    "end": 9,
                }
            ],
        }
    )

    msb_results = verify_parity(bits, fmt_msb)
    lsb_results = verify_parity(bits, fmt_lsb)

    assert [row["parity_bit"] for row in msb_results] == [0, 5]
    assert [row["parity_bit"] for row in lsb_results] == [4, 9]


def test_new_wiegand_formats_compute_parity():
    formats_to_test = [
        (
            "Wiegand-36 (Siemens)",
            [5, 22],
            [
                (1, 17, "even", 0),
                (18, 34, "odd", 35),
            ],
        ),
        (
            "Wiegand-39 (Pyramid)",
            [8, 30],
            [
                (1, 19, "even", 0),
                (20, 37, "odd", 38),
            ],
        ),
        (
            "Wiegand-42 (Lenel)",
            [12, 28, 37],
            [
                (1, 20, "even", 0),
                (21, 40, "odd", 41),
            ],
        ),
        (
            "Wiegand-37 (Generic)",
            [4, 15, 27],
            [
                (1, 18, "even", 0),
                (19, 35, "odd", 36),
            ],
        ),
    ]

    for name, ones_positions, parity_specs in formats_to_test:
        fmt = load_format(name)
        bits = ["0"] * fmt.bit_length
        for pos in ones_positions:
            bits[pos] = "1"
        for start, end, parity_type, parity_bit_index in parity_specs:
            fill_parity_bit(bits, start, end, parity_type, parity_bit_index)
        payload = "".join(bits)
        parity = verify_parity(payload, fmt)
        stats = parity_score(parity)
        assert stats["gated_fail"] == 0, f"{name} parity failed"
        assert stats["total_fail"] == 0, f"{name} parity failed"


def test_wiegand_50_parity():
    fmt = load_format("Wiegand-50 (Generic)")
    bits = ["0"] * fmt.bit_length
    for pos in (5, 24, 30, 49):
        bits[pos] = "1"
    # Compute odd parity for the right half first (uses bit 25 as the parity bit)
    fill_parity_bit(bits, 26, 49, "odd", 25)
    # Then compute even parity for the left half (bit 1 is the parity bit, and the coverage includes bit 25)
    fill_parity_bit(bits, 2, 25, "even", 1)
    payload = "".join(bits)
    parity = verify_parity(payload, fmt)
    stats = parity_score(parity)
    assert stats["gated_fail"] == 0
    assert stats["total_fail"] == 0
