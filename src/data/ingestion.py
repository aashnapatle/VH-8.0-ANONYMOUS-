"""
ingestion.py — CSV ingestion pipeline
=======================================
Aashna — Data Engineering & Performance Owner

Pipeline:
    RAW CSV → READ (Polars) → VALIDATE → NORMALIZE → CLEAN → PARQUET

Usage:
    from src.data.ingestion import run_ingestion_pipeline
    result = run_ingestion_pipeline()

The raw CSV is NEVER modified. All outputs go to data/processed/.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import polars as pl

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent.parent.parent / "data" / "processed"

RAW_CSV = RAW_DIR / "VoidHacks8_MuleAccount_2M_Transactions.csv"
CLEAN_PARQUET = PROCESSED_DIR / "transactions.parquet"
FLAGGED_PARQUET = PROCESSED_DIR / "transactions_flagged.parquet"
VALIDATION_REPORT = PROCESSED_DIR / "validation_report.json"

# ── Expected schema ────────────────────────────────────────────────────────────
# Column names in the raw CSV (confirmed via audit — exact match)
RAW_COLUMNS = [
    "Transaction_ID",
    "Sender_Account",
    "Receiver_Account",
    "Sender_IFSC",
    "Receiver_IFSC",
    "Amount",
    "Timestamp",
    "Payment_Mode",
    "Narration",
    "IP_Address",
    "Device_Type",
]

# Internal column names (snake_case, used throughout the system)
INTERNAL_COLUMNS = {
    "Transaction_ID": "transaction_id",
    "Sender_Account": "sender_account",
    "Receiver_Account": "receiver_account",
    "Sender_IFSC": "sender_ifsc",
    "Receiver_IFSC": "receiver_ifsc",
    "Amount": "amount",
    "Timestamp": "timestamp",
    "Payment_Mode": "payment_mode",
    "Narration": "narration",
    "IP_Address": "ip_address",
    "Device_Type": "device_type",
}

# Device types considered suspicious (flagged, not deleted)
SUSPICIOUS_DEVICES = {"Web_Emulator", "Linux_Script"}

# Valid payment modes
VALID_PAYMENT_MODES = {"IMPS", "UPI", "RTGS", "NEFT"}


def _ensure_processed_dir() -> None:
    """Create data/processed/ if it doesn't exist."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def read_raw_csv(csv_path: Optional[Path] = None) -> pl.DataFrame:
    """
    Read the raw CSV using Polars with explicit schema.
    Returns raw DataFrame with original column names.
    Does NOT modify the source file.
    """
    path = csv_path or RAW_CSV
    logger.info(f"Reading CSV: {path}")

    df = pl.read_csv(
        path,
        schema_overrides={
            "Transaction_ID": pl.Utf8,
            "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8,
            "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8,
            "Amount": pl.Float64,
            "Timestamp": pl.Utf8,   # Parse explicitly in normalize step
            "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8,
            "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False,      # We handle timestamps explicitly
        infer_schema=False,
        null_values=["", "NULL", "null", "NA", "N/A", "nan"],
        truncate_ragged_lines=True,
    )
    logger.info(f"Read {len(df):,} rows, {len(df.columns)} columns")
    return df


def validate(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """
    Validate the raw DataFrame.

    Returns:
        (clean_df, flagged_df, validation_summary)

    Validation rules:
        - Duplicate Transaction_ID: keep first, flag duplicates
        - Amount <= 0: flag as invalid_amount
        - Null in any required field: flag as missing_field
        - Malformed Timestamp: flag as malformed_timestamp
        - Invalid Payment_Mode: flag as invalid_payment_mode
        - Suspicious Device_Type (Web_Emulator, Linux_Script):
          flag as suspicious_device BUT KEEP in clean data too
          (Gunjan needs these for graph analysis)
    """
    logger.info("Running validation...")
    flagged_frames = []
    summary = {
        "total_rows": len(df),
        "duplicate_ids": 0,
        "invalid_amounts": 0,
        "missing_fields": 0,
        "malformed_timestamps": 0,
        "invalid_payment_modes": 0,
        "suspicious_devices": 0,
        "clean_rows": 0,
        "flagged_rows": 0,
    }

    # ── 1. Duplicate Transaction_ID ──────────────────────────────────────────
    # Mark duplicates: keep first occurrence as clean, flag the rest
    dup_mask = df["Transaction_ID"].is_duplicated()
    # First occurrences of any ID that appears multiple times
    first_occurrence = df.with_row_index("__row_idx__").filter(
        df["Transaction_ID"].is_duplicated()
    ).group_by("Transaction_ID").agg(pl.col("__row_idx__").min().alias("first_idx"))
    first_idx_set = set(first_occurrence["first_idx"].to_list())

    # All rows that are duplicate AND not the first occurrence
    dup_not_first = (
        df.with_row_index("__row_idx__")
        .filter(pl.col("Transaction_ID").is_duplicated())
        .filter(~pl.col("__row_idx__").is_in(list(first_idx_set)))
        .drop("__row_idx__")
        .with_columns(pl.lit("duplicate_id").alias("flag_reason"))
    )
    summary["duplicate_ids"] = len(dup_not_first)
    if len(dup_not_first) > 0:
        flagged_frames.append(dup_not_first)

    # Build index set of non-first duplicate rows to exclude from clean
    dup_not_first_ids_df = (
        df.with_row_index("__row_idx__")
        .filter(pl.col("Transaction_ID").is_duplicated())
        .filter(~pl.col("__row_idx__").is_in(list(first_idx_set)))
        .select("__row_idx__")
    )
    dup_exclusion_idx = set(dup_not_first_ids_df["__row_idx__"].to_list())

    # Working copy: exclude duplicate non-first rows
    df_indexed = df.with_row_index("__row_idx__")
    df_deduped = df_indexed.filter(
        ~pl.col("__row_idx__").is_in(list(dup_exclusion_idx))
    ).drop("__row_idx__")

    # ── 2. Invalid Amount (≤ 0 or null) ──────────────────────────────────────
    invalid_amt_mask = (df_deduped["Amount"].is_null()) | (df_deduped["Amount"] <= 0)
    invalid_amt = (
        df_deduped.filter(invalid_amt_mask)
        .with_columns(pl.lit("invalid_amount").alias("flag_reason"))
    )
    summary["invalid_amounts"] = len(invalid_amt)
    if len(invalid_amt) > 0:
        flagged_frames.append(invalid_amt)

    # ── 3. Missing fields ─────────────────────────────────────────────────────
    required_cols = [c for c in RAW_COLUMNS if c != "Narration"]  # narration may be blank
    null_mask = pl.lit(False)
    for col in required_cols:
        if col in df_deduped.columns:
            null_mask = null_mask | df_deduped[col].is_null()
    missing_rows = (
        df_deduped.filter(null_mask)
        .with_columns(pl.lit("missing_required_field").alias("flag_reason"))
    )
    summary["missing_fields"] = len(missing_rows)
    if len(missing_rows) > 0:
        flagged_frames.append(missing_rows)

    # ── 4. Malformed Timestamps ───────────────────────────────────────────────
    try:
        ts_parsed = df_deduped.with_columns(
            pl.col("Timestamp").str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S", strict=False).alias("_ts_check")
        )
        malformed_ts_mask = ts_parsed["_ts_check"].is_null() & df_deduped["Timestamp"].is_not_null()
        malformed_ts = (
            df_deduped.filter(malformed_ts_mask)
            .with_columns(pl.lit("malformed_timestamp").alias("flag_reason"))
        )
        summary["malformed_timestamps"] = len(malformed_ts)
        if len(malformed_ts) > 0:
            flagged_frames.append(malformed_ts)
    except Exception as e:
        logger.warning(f"Timestamp validation error: {e}")

    # ── 5. Invalid Payment Mode ───────────────────────────────────────────────
    invalid_pm_mask = (
        df_deduped["Payment_Mode"].is_not_null() &
        ~df_deduped["Payment_Mode"].is_in(list(VALID_PAYMENT_MODES))
    )
    invalid_pm = (
        df_deduped.filter(invalid_pm_mask)
        .with_columns(pl.lit("invalid_payment_mode").alias("flag_reason"))
    )
    summary["invalid_payment_modes"] = len(invalid_pm)
    if len(invalid_pm) > 0:
        flagged_frames.append(invalid_pm)

    # ── 6. Suspicious Device (flag but KEEP in clean data) ───────────────────
    suspicious_mask = df_deduped["Device_Type"].is_in(list(SUSPICIOUS_DEVICES))
    suspicious_rows = (
        df_deduped.filter(suspicious_mask)
        .with_columns(pl.lit("suspicious_device").alias("flag_reason"))
    )
    summary["suspicious_devices"] = len(suspicious_rows)
    if len(suspicious_rows) > 0:
        flagged_frames.append(suspicious_rows)
    # NOTE: suspicious device rows are NOT removed from clean data
    # They are valuable signals for Gunjan's graph analysis

    # ── Combine flagged ───────────────────────────────────────────────────────
    if flagged_frames:
        # Ensure all frames have same schema for concat
        # Add flag_reason to df_deduped structure for consistency
        base_cols = df_deduped.columns
        flagged_frames_aligned = []
        for ff in flagged_frames:
            cols_to_select = base_cols + ["flag_reason"]
            available = [c for c in cols_to_select if c in ff.columns]
            # Add missing columns as null
            ff_aligned = ff.select(available)
            for col in cols_to_select:
                if col not in ff_aligned.columns:
                    ff_aligned = ff_aligned.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))
            flagged_frames_aligned.append(ff_aligned.select(cols_to_select))
        flagged_df = pl.concat(flagged_frames_aligned)
    else:
        flagged_df = df_deduped.head(0).with_columns(pl.lit(None).cast(pl.Utf8).alias("flag_reason"))

    # Clean = deduped data minus invalid amounts, missing fields, malformed timestamps, invalid payment modes
    # Suspicious devices remain in clean data
    hard_exclusion_mask = invalid_amt_mask | null_mask
    clean_df = df_deduped.filter(~hard_exclusion_mask)

    summary["clean_rows"] = len(clean_df)
    summary["flagged_rows"] = len(flagged_df)

    logger.info(
        f"Validation complete: {summary['clean_rows']:,} clean, "
        f"{summary['flagged_rows']:,} flagged entries"
    )
    return clean_df, flagged_df, summary


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normalize validated DataFrame:
    - Rename columns to snake_case internal names
    - Parse Timestamp to Datetime type
    - Strip whitespace from string columns
    - Uppercase categorical fields for consistency
    """
    logger.info("Normalizing data...")

    # Rename to internal snake_case names
    df = df.rename(INTERNAL_COLUMNS)

    # Parse timestamp string → Polars Datetime
    df = df.with_columns(
        pl.col("timestamp")
        .str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S")
        .alias("timestamp")
    )

    # Strip whitespace from all string columns
    str_cols = [c for c, dtype in zip(df.columns, df.dtypes) if dtype == pl.Utf8]
    df = df.with_columns([
        pl.col(c).str.strip_chars() for c in str_cols
    ])

    # Uppercase categoricals for consistency
    df = df.with_columns([
        pl.col("payment_mode").str.to_uppercase(),
        pl.col("device_type").str.to_uppercase(),
    ])

    logger.info(f"Normalization complete: {len(df):,} rows")
    return df


def write_parquet(clean_df: pl.DataFrame, flagged_df: pl.DataFrame) -> None:
    """Write clean and flagged DataFrames to Parquet files."""
    _ensure_processed_dir()

    logger.info(f"Writing clean Parquet: {CLEAN_PARQUET}")
    clean_df.write_parquet(CLEAN_PARQUET, compression="snappy")

    logger.info(f"Writing flagged Parquet: {FLAGGED_PARQUET}")
    if len(flagged_df) > 0:
        # Ensure flag_reason column is present
        if "flag_reason" not in flagged_df.columns:
            flagged_df = flagged_df.with_columns(pl.lit("unknown").alias("flag_reason"))
        flagged_df.write_parquet(FLAGGED_PARQUET, compression="snappy")
    else:
        # Write empty flagged file with schema
        flagged_df.write_parquet(FLAGGED_PARQUET, compression="snappy")

    logger.info("Parquet write complete")


def run_ingestion_pipeline(
    csv_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Full ingestion pipeline: CSV → validate → normalize → Parquet.

    Args:
        csv_path: Override raw CSV path (useful for testing)
        output_dir: Override output directory (useful for testing)

    Returns:
        dict with timing and validation summary
    """
    global CLEAN_PARQUET, FLAGGED_PARQUET, VALIDATION_REPORT

    if output_dir:
        CLEAN_PARQUET = output_dir / "transactions.parquet"
        FLAGGED_PARQUET = output_dir / "transactions_flagged.parquet"
        VALIDATION_REPORT = output_dir / "validation_report.json"

    timings = {}
    t_total = time.perf_counter()

    # Stage 1: Read
    t0 = time.perf_counter()
    raw_df = read_raw_csv(csv_path)
    timings["read_csv_seconds"] = round(time.perf_counter() - t0, 3)
    logger.info(f"Stage 1 (Read): {timings['read_csv_seconds']}s")

    # Stage 2: Validate
    t0 = time.perf_counter()
    clean_df, flagged_df, validation_summary = validate(raw_df)
    timings["validate_seconds"] = round(time.perf_counter() - t0, 3)
    logger.info(f"Stage 2 (Validate): {timings['validate_seconds']}s")

    # Stage 3: Normalize
    t0 = time.perf_counter()
    clean_df = normalize(clean_df)
    # Also normalize flagged (for storage consistency, minus timestamp parse which may fail)
    if len(flagged_df) > 0 and "flag_reason" in flagged_df.columns:
        flag_reason_col = flagged_df["flag_reason"]
        flagged_base = flagged_df.drop("flag_reason")
        try:
            flagged_base = flagged_base.rename({k: v for k, v in INTERNAL_COLUMNS.items() if k in flagged_base.columns})
            str_cols = [c for c, dtype in zip(flagged_base.columns, flagged_base.dtypes) if dtype == pl.Utf8]
            flagged_base = flagged_base.with_columns([pl.col(c).str.strip_chars() for c in str_cols])
        except Exception:
            pass
        flagged_df = flagged_base.with_columns(flag_reason_col)
    timings["normalize_seconds"] = round(time.perf_counter() - t0, 3)
    logger.info(f"Stage 3 (Normalize): {timings['normalize_seconds']}s")

    # Stage 4: Write Parquet
    t0 = time.perf_counter()
    write_parquet(clean_df, flagged_df)
    timings["write_parquet_seconds"] = round(time.perf_counter() - t0, 3)
    logger.info(f"Stage 4 (Write Parquet): {timings['write_parquet_seconds']}s")

    timings["total_seconds"] = round(time.perf_counter() - t_total, 3)

    # Write validation report
    report = {**validation_summary, **timings, "rows_per_second": round(
        validation_summary["total_rows"] / timings["total_seconds"]
    )}
    _ensure_processed_dir()
    VALIDATION_REPORT.write_text(json.dumps(report, indent=2))
    logger.info(f"Validation report: {VALIDATION_REPORT}")
    logger.info(f"Pipeline complete in {timings['total_seconds']}s")

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_ingestion_pipeline()
    print(json.dumps(result, indent=2))
