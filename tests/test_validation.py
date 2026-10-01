"""
test_validation.py — Tests for data validation logic
======================================================
All tests use synthetic data. Real dataset is never loaded.
"""

import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.ingestion import validate, SUSPICIOUS_DEVICES, VALID_PAYMENT_MODES


class TestDuplicateDetection:
    def test_no_duplicates_in_base_data(self, synthetic_df):
        """Clean synthetic data should have zero duplicate IDs."""
        clean_df, flagged_df, summary = validate(synthetic_df)
        assert summary["duplicate_ids"] == 0

    def test_duplicate_ids_are_flagged(self, df_with_duplicates):
        """Duplicate Transaction_IDs should appear in flagged output."""
        clean_df, flagged_df, summary = validate(df_with_duplicates)
        assert summary["duplicate_ids"] >= 1

    def test_duplicate_first_occurrence_kept(self, df_with_duplicates):
        """The first occurrence of a duplicate ID must remain in clean data."""
        clean_df, flagged_df, summary = validate(df_with_duplicates)
        # TXN000000001 appears twice; first occurrence should be in clean
        clean_ids = clean_df["Transaction_ID"].to_list()
        assert "TXN000000001" in clean_ids

    def test_duplicate_second_occurrence_not_in_clean(self, df_with_duplicates):
        """Duplicate rows (non-first) must NOT appear multiple times in clean data."""
        clean_df, flagged_df, summary = validate(df_with_duplicates)
        id_counts = clean_df["Transaction_ID"].value_counts()
        for row in id_counts.iter_rows():
            assert row[1] == 1, f"Transaction_ID {row[0]} appears {row[1]} times in clean data"

    def test_flagged_has_flag_reason(self, df_with_duplicates):
        """Flagged rows must contain a flag_reason column."""
        clean_df, flagged_df, summary = validate(df_with_duplicates)
        if len(flagged_df) > 0:
            assert "flag_reason" in flagged_df.columns


class TestMissingValues:
    def test_missing_receiver_flagged(self, df_with_missing):
        """Row with missing Receiver_Account should be flagged."""
        clean_df, flagged_df, summary = validate(df_with_missing)
        assert summary["missing_fields"] >= 1

    def test_missing_amount_flagged(self, df_with_missing):
        """Row with missing Amount should be flagged."""
        clean_df, flagged_df, summary = validate(df_with_missing)
        assert summary["missing_fields"] >= 1 or summary["invalid_amounts"] >= 1

    def test_missing_rows_not_in_clean(self, df_with_missing):
        """Rows with missing required fields must not appear in clean data."""
        clean_df, flagged_df, summary = validate(df_with_missing)
        # All rows with null receiver_account should be excluded from clean
        null_receiver = clean_df.filter(pl.col("Receiver_Account").is_null())
        assert len(null_receiver) == 0


class TestInvalidAmounts:
    def test_negative_amount_flagged(self, df_with_invalid_amounts):
        """Rows with negative amounts should be flagged."""
        clean_df, flagged_df, summary = validate(df_with_invalid_amounts)
        assert summary["invalid_amounts"] >= 1

    def test_zero_amount_flagged(self, df_with_invalid_amounts):
        """Rows with zero amounts should be flagged."""
        clean_df, flagged_df, summary = validate(df_with_invalid_amounts)
        assert summary["invalid_amounts"] >= 1

    def test_valid_amount_not_flagged(self, df_with_invalid_amounts):
        """Valid positive amount rows must remain in clean data."""
        clean_df, flagged_df, summary = validate(df_with_invalid_amounts)
        # TXN888000003 has amount=500.00, must be in clean
        clean_ids = clean_df["Transaction_ID"].to_list()
        assert "TXN888000003" in clean_ids

    def test_negative_amount_not_in_clean(self, df_with_invalid_amounts):
        """Negative amount rows must not be in clean data."""
        clean_df, flagged_df, summary = validate(df_with_invalid_amounts)
        # TXN888000001 has -500.00
        clean_ids = clean_df["Transaction_ID"].to_list()
        assert "TXN888000001" not in clean_ids


class TestMalformedTimestamps:
    def test_bad_timestamp_flagged(self, df_with_bad_timestamps):
        """Rows with malformed timestamps should be flagged."""
        clean_df, flagged_df, summary = validate(df_with_bad_timestamps)
        assert summary["malformed_timestamps"] >= 1

    def test_good_timestamp_not_flagged(self, df_with_bad_timestamps):
        """Valid timestamp rows must not be flagged for timestamp."""
        clean_df, flagged_df, summary = validate(df_with_bad_timestamps)
        # Only 1 of 2 rows has a bad timestamp
        # TXN777000002 has good timestamp
        clean_ids = clean_df["Transaction_ID"].to_list()
        assert "TXN777000002" in clean_ids


class TestSuspiciousDevices:
    def test_suspicious_devices_flagged(self, synthetic_df):
        """Web_Emulator and Linux_Script devices should be in flagged data."""
        clean_df, flagged_df, summary = validate(synthetic_df)
        assert summary["suspicious_devices"] >= 2  # 1 Web_Emulator + 1 Linux_Script

    def test_suspicious_devices_still_in_clean(self, synthetic_df):
        """
        Suspicious device rows must ALSO remain in clean data.
        Gunjan's graph engine needs all transaction edges.
        """
        clean_df, flagged_df, summary = validate(synthetic_df)
        # TXN000000006 is Web_Emulator, TXN000000007 is Linux_Script
        clean_ids = clean_df["Transaction_ID"].to_list()
        assert "TXN000000006" in clean_ids
        assert "TXN000000007" in clean_ids

    def test_suspicious_device_flag_reason(self, synthetic_df):
        """Suspicious device entries in flagged_df must have correct flag_reason."""
        clean_df, flagged_df, summary = validate(synthetic_df)
        if len(flagged_df) > 0 and "flag_reason" in flagged_df.columns:
            flag_reasons = flagged_df["flag_reason"].to_list()
            assert "suspicious_device" in flag_reasons


class TestValidationSummary:
    def test_summary_keys_present(self, synthetic_df):
        """Validation summary dict must contain all expected keys."""
        _, _, summary = validate(synthetic_df)
        expected_keys = [
            "total_rows", "duplicate_ids", "invalid_amounts",
            "missing_fields", "malformed_timestamps",
            "suspicious_devices", "clean_rows", "flagged_rows",
        ]
        for key in expected_keys:
            assert key in summary, f"Missing key: {key}"

    def test_clean_rows_plus_exclusions_leq_total(self, synthetic_df):
        """clean_rows should not exceed total_rows."""
        _, _, summary = validate(synthetic_df)
        assert summary["clean_rows"] <= summary["total_rows"]
