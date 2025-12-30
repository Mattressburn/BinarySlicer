import pytest

from binaryslicer.formats import (
    FormatRepository,
    FormatValidationError,
    find_best_offsets,
    normalize_format_entry,
    validate_format_entry,
)


def test_bundled_formats_validate():
    repo = FormatRepository()
    assert repo.last_errors == []
    assert repo.formats  # ensure at least one format loaded


def test_validate_rejects_bad_ranges_and_allows_single_bit():
    good = {"name": "One Bit", "bit_length": 8, "fields": [{"name": "Only", "start": 3, "end": 3}]}
    validate_format_entry(good, normalize_format_entry(good))

    bad = {"name": "Bad Field", "bit_length": 4, "fields": [{"name": "oops", "start": 2, "end": 1}]}
    with pytest.raises(FormatValidationError):
        validate_format_entry(bad, normalize_format_entry(bad))


def test_validate_detects_overlaps():
    entry = {
        "name": "Overlap",
        "bit_length": 8,
        "fields": [
            {"name": "A", "start": 0, "end": 3},
            {"name": "B", "start": 3, "end": 5},
        ],
    }
    with pytest.raises(FormatValidationError):
        validate_format_entry(entry, normalize_format_entry(entry))

    entry["fields"][1]["hidden"] = True
    validate_format_entry(entry, normalize_format_entry(entry))


def test_auto_offset_scoring_prefers_parity_pass():
    fmt_entry = {
        "name": "AutoParity",
        "bit_length": 4,
        "fields": [{"name": "Data", "start": 0, "end": 3}],
        "parity": [
            {
                "type": "even",
                "per_character": True,
                "character_width": 2,
                "parity_position": "lsb",
            }
        ],
    }
    fmt = normalize_format_entry(fmt_entry)
    binary = "010011"  # only offset 2 -> 0011 satisfies both parity checks
    results = find_best_offsets(binary, fmt, step=1, top_n=3)
    assert results
    best = results[0]
    assert best["offset"] == 2
    assert best["stats"]["gated_fail"] == 0
