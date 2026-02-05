"""Regression tests for HID Corporate 1000 35-bit format.

These tests verify the fix for Corporate 1000 slicing that requires:
- MSB-aligned extraction of 35 used bits from longer payloads (40 or 64 bits)
- Correct 0-based field indexing:
  - Parity 1: bit 0
  - Parity 2: bit 1
  - Facility Code: bits 2-13 (12 bits)
  - Card Number: bits 14-33 (20 bits)
  - Parity 3: bit 34
"""

import pytest
from binaryslicer.controller import Controller
from binaryslicer.decoder import process_input
from binaryslicer.formats import (
    FormatRepository,
    extract_used_region,
    prepare_bits_for_format,
    slice_field_1based,
)


class TestCorporate1000Helpers:
    """Test the helper functions used for MSB-aligned extraction."""

    def test_extract_used_region_msb_alignment(self):
        """MSB alignment should take the leftmost bits."""
        binary = "1011001011110000011101001111111011000000"  # 40 bits
        result = extract_used_region(binary, 35, "msb")
        assert result == "10110010111100000111010011111110110"
        assert len(result) == 35

    def test_extract_used_region_lsb_alignment(self):
        """LSB alignment should take the rightmost bits."""
        binary = "1011001011110000011101001111111011000000"  # 40 bits
        result = extract_used_region(binary, 35, "lsb")
        assert result == "01011110000011101001111111011000000"  # last 35 bits
        assert len(result) == 35

    def test_extract_used_region_shorter_input(self):
        """If input is shorter than used_bits, return full input."""
        binary = "1011001011110000"  # 16 bits
        result = extract_used_region(binary, 35, "msb")
        assert result == binary

    def test_slice_field_1based(self):
        """1-based slicing should work correctly."""
        bits = "10110010111100000111010011111110110"  # 35 bits
        # FC: bits 3-14 (1-based), length 12
        fc = slice_field_1based(bits, 3, 12)
        assert fc == 3260
        # CN: bits 15-34 (1-based), length 20
        cn = slice_field_1based(bits, 15, 20)
        assert cn == 119803


class TestCorporate1000FormatDefinition:
    """Test that the format definition is correct."""

    def test_format_has_used_bits(self):
        """Corporate 1000 35-bit should have used_bits=35."""
        repo = FormatRepository()
        fmt = repo.formats.get("HID Corporate 1000 - 35-bit")
        assert fmt is not None
        assert fmt.used_bits == 35
        assert fmt.used_bits_alignment == "msb"

    def test_format_field_positions(self):
        """Verify field positions using 0-based indexing."""
        repo = FormatRepository()
        fmt = repo.formats.get("HID Corporate 1000 - 35-bit")
        assert fmt is not None

        # Check field ranges (0-based, inclusive)
        assert fmt.fields.get("Parity 1") == (0, 0)
        assert fmt.fields.get("Parity 2") == (1, 1)
        assert fmt.fields.get("Company ID (Facility)") == (2, 13)
        assert fmt.fields.get("Card Number") == (14, 33)
        assert fmt.fields.get("Parity 3") == (34, 34)

    def test_prepare_bits_for_format(self):
        """prepare_bits_for_format should extract MSB region."""
        repo = FormatRepository()
        fmt = repo.formats.get("HID Corporate 1000 - 35-bit")
        binary = "1011001011110000011101001111111011000000"  # 40 bits
        prepared = prepare_bits_for_format(binary, fmt)
        assert prepared == "10110010111100000111010011111110110"
        assert len(prepared) == 35


class TestCorporate1000Decoding:
    """Integration tests for Corporate 1000 decoding."""

    def test_decode_b2f074fec0_known_good(self):
        """
        Regression test for known-good sample.

        Input: B2F074FEC0 (hex, 40 bits)
        Expected output:
        - Facility Code: 3260
        - Card Number: 119803
        - Parity 1: 1 (bit 0)
        - Parity 2: 0 (bit 1)
        - Parity 3: 0 (bit 34)
        """
        ctrl = Controller()
        result = ctrl.analyze_input("B2F074FEC0", slice_mode="auto")

        # Find the Corporate 1000 rows
        corp_rows = [row for row in result.table_rows if "Corporate 1000" in row.format_name]
        assert len(corp_rows) > 0, "No Corporate 1000 results found"

        # Extract field values
        values = {row.field: int(row.value) for row in corp_rows}

        # Verify expected values
        assert values.get("Company ID (Facility)") == 3260, f"Expected FC=3260, got {values.get('Company ID (Facility)')}"
        assert values.get("Card Number") == 119803, f"Expected CN=119803, got {values.get('Card Number')}"
        assert values.get("Parity 1") == 1, f"Expected P1=1, got {values.get('Parity 1')}"
        assert values.get("Parity 2") == 0, f"Expected P2=0, got {values.get('Parity 2')}"
        assert values.get("Parity 3") == 0, f"Expected P3=0, got {values.get('Parity 3')}"

    def test_decode_b2f074fec0_binary_input(self):
        """Test with direct binary input (35 bits)."""
        ctrl = Controller()
        # Direct 35-bit input (no padding)
        binary_35 = "10110010111100000111010011111110110"
        result = ctrl.analyze_input(binary_35, slice_mode="auto")

        corp_rows = [row for row in result.table_rows if "Corporate 1000" in row.format_name]
        values = {row.field: int(row.value) for row in corp_rows}

        assert values.get("Company ID (Facility)") == 3260
        assert values.get("Card Number") == 119803

    def test_decode_64bit_padded_input(self):
        """Test with 64-bit padded input (Corporate 1000 in MSB portion)."""
        ctrl = Controller()
        # B2F074FEC0 padded to 64 bits with trailing zeros
        hex_64 = "B2F074FEC0000000"
        result = ctrl.analyze_input(hex_64, slice_mode="auto")

        # Filter specifically for "35-bit" format to avoid 48-bit variant
        corp_rows = [row for row in result.table_rows if "Corporate 1000 - 35-bit" in row.format_name]
        values = {row.field: int(row.value) for row in corp_rows}

        assert values.get("Company ID (Facility)") == 3260
        assert values.get("Card Number") == 119803

    def test_corporate_1000_is_best_match_for_test_data(self):
        """Corporate 1000 should be selected as best format for valid C1000 data."""
        ctrl = Controller()
        result = ctrl.analyze_input("B2F074FEC0", slice_mode="auto")

        # Best format should be Corporate 1000 (format with aligned MSB extraction)
        assert result.best_format is not None
        assert "Corporate 1000" in result.best_format


class TestCorporate1000ParityBits:
    """Test parity bit extraction positions."""

    def test_parity_bit_positions(self):
        """Verify parity bits are at correct positions in 35-bit region."""
        binary = "10110010111100000111010011111110110"  # Known test data

        # Using 0-based indexing
        p1 = int(binary[0])   # Bit 0 (1-based: bit 1)
        p2 = int(binary[1])   # Bit 1 (1-based: bit 2)
        p35 = int(binary[34]) # Bit 34 (1-based: bit 35)

        assert p1 == 1, f"Parity 1 should be 1, got {p1}"
        assert p2 == 0, f"Parity 2 should be 0, got {p2}"
        assert p35 == 0, f"Parity 3 should be 0, got {p35}"

    def test_parity_bits_extracted_by_controller(self):
        """Controller should extract parity bits at correct indices."""
        ctrl = Controller()
        result = ctrl.analyze_input("B2F074FEC0", slice_mode="auto")

        corp_rows = [row for row in result.table_rows if "Corporate 1000" in row.format_name]

        # Find parity rows and check their ranges (0-based)
        parity_rows = {row.field: row.range for row in corp_rows if "Parity" in row.field}

        assert "Parity 1" in parity_rows
        assert parity_rows["Parity 1"] == "0–0"
        assert "Parity 2" in parity_rows
        assert parity_rows["Parity 2"] == "1–1"
        assert "Parity 3" in parity_rows
        assert parity_rows["Parity 3"] == "34–34"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
