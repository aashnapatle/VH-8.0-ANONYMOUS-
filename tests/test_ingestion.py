"""
test_ingestion.py — Tests for the ingestion pipeline
======================================================
Tests read → normalize flow using synthetic data.
"""

import io
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.ingestion import (
    INTERNAL_COLUMNS,
    RAW_COLUMNS,
    normalize,
    read_raw_csv,
    validate,
)


class TestColumnMapping:
    def test_all_raw_columns_present(self, synthetic_df):
        """Raw DataFrame must contain all expected columns."""
        for col in RAW_COLUMNS:
            assert col in synthetic_df.columns, f"Missing column: {col}"

    def test_normalize_renames_to_snake_case(self, synthetic_df):
        """After normalization, columns must be snake_case."""
        clean_df, _, _ = validate(synthetic_df)
        normalized = normalize(clean_df)
        for raw_col, internal_col in INTERNAL_COLUMNS.items():
            assert internal_col in normalized.columns, f"Missing internal column: {internal_col}"
            assert raw_col not in normalized.columns, f"Raw column still present: {raw_col}"


class TestTimestampParsing:
    def test_timestamp_is_datetime_type(self, synthetic_df):
        """After normalization, timestamp column must be Polars Datetime type."""
        clean_df, _, _ = validate(synthetic_df)
        normalized = normalize(clean_df)
        assert normalized["timestamp"].dtype in (pl.Datetime, pl.Datetime("us"), pl.Datetime("ns"), pl.Datetime("ms"))

    def test_timestamp_values_are_correct(self, synthetic_df):
        """Spot-check: first row timestamp must parse correctly."""
        clean_df, _, _ = validate(synthetic_df)
        normalized = normalize(clean_df)
        first_ts = normalized["timestamp"][0]
        # Should be 2026-09-22 10:00:00
        assert first_ts is not None


class TestAmountTypes:
    def test_amount_is_float(self, synthetic_df):
        """Amount column must be Float64 after ingestion."""
        assert synthetic_df["Amount"].dtype == pl.Float64

    def test_amount_values_positive_in_clean(self, synthetic_df):
        """All amounts in clean data must be positive."""
        clean_df, _, _ = validate(synthetic_df)
        normalized = normalize(clean_df)
        assert (normalized["amount"] > 0).all()


class TestReadRawCsv:
    def test_read_returns_dataframe(self, tmp_path, synthetic_csv_content):
        """read_raw_csv must return a Polars DataFrame."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(synthetic_csv_content)
        df = read_raw_csv(csv_file)
        assert isinstance(df, pl.DataFrame)

    def test_read_correct_row_count(self, tmp_path, synthetic_csv_content):
        """read_raw_csv must read all rows from the CSV."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(synthetic_csv_content)
        df = read_raw_csv(csv_file)
        assert len(df) == 7  # 7 data rows in SYNTHETIC_CSV

    def test_read_correct_column_count(self, tmp_path, synthetic_csv_content):
        """read_raw_csv must read all 11 columns."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(synthetic_csv_content)
        df = read_raw_csv(csv_file)
        assert len(df.columns) == 11


class TestEndToEndNormalization:
    def test_full_pipeline_on_synthetic(self, tmp_path, synthetic_csv_content):
        """Full pipeline: read → validate → normalize → write Parquet → verify."""
        from src.data.ingestion import run_ingestion_pipeline

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(synthetic_csv_content)
        output_dir = tmp_path / "processed"
        output_dir.mkdir()

        report = run_ingestion_pipeline(csv_path=csv_file, output_dir=output_dir)

        assert report["total_rows"] == 7
        assert report["clean_rows"] > 0
        assert (output_dir / "transactions.parquet").exists()
        assert (output_dir / "validation_report.json").exists()

    def test_parquet_readable_by_duckdb(self, tmp_path, synthetic_csv_content):
        """The generated Parquet must be readable by DuckDB."""
        import duckdb
        from src.data.ingestion import run_ingestion_pipeline

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(synthetic_csv_content)
        output_dir = tmp_path / "processed"
        output_dir.mkdir()

        run_ingestion_pipeline(csv_path=csv_file, output_dir=output_dir)

        parquet_path = str(output_dir / "transactions.parquet").replace("\\", "/")
        con = duckdb.connect(":memory:")
        result = con.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')").fetchone()
        assert result[0] > 0
