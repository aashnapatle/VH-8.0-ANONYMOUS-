"""
conftest.py — pytest fixtures for data layer unit tests
=========================================================
All fixtures use SMALL SYNTHETIC DATASETS.
The real 273 MB dataset is NEVER loaded during unit tests.
"""

import io
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Synthetic CSV content ──────────────────────────────────────────────────────

SYNTHETIC_CSV = """\
Transaction_ID,Sender_Account,Receiver_Account,Sender_IFSC,Receiver_IFSC,Amount,Timestamp,Payment_Mode,Narration,IP_Address,Device_Type
TXN000000001,ACCT00000001,ACCT00000002,BANK0001000,BANK0002000,50000.00,2026-09-22 10:00:00,UPI,UPI/P2P/TEST,192.168.1.1,Android
TXN000000002,ACCT00000002,ACCT00000003,BANK0002000,BANK0003000,25000.00,2026-09-22 10:05:00,IMPS,IMPS/TEST,192.168.1.2,iOS
TXN000000003,ACCT00000001,ACCT00000003,BANK0001000,BANK0003000,10000.00,2026-09-22 10:10:00,NEFT,NEFT/TEST,192.168.1.3,Windows_Browser
TXN000000004,ACCT00000003,ACCT00000001,BANK0003000,BANK0001000,5000.00,2026-09-22 10:15:00,RTGS,RTGS/TEST,192.168.1.4,Android
TXN000000005,ACCT00000002,ACCT00000001,BANK0002000,BANK0001000,15000.00,2026-09-22 10:20:00,UPI,UPI/P2P/TEST2,192.168.1.5,iOS
TXN000000006,ACCT00000004,ACCT00000001,BANK0004000,BANK0001000,99999.99,2026-09-22 11:00:00,UPI,UPI/SUSPICIOUS,10.10.10.1,Web_Emulator
TXN000000007,ACCT00000005,ACCT00000001,BANK0005000,BANK0001000,1000.00,2026-09-23 09:00:00,UPI,UPI/P2P/SMALL,10.20.20.2,Linux_Script
"""

# Duplicate ID version (TXN000000001 appears twice)
SYNTHETIC_CSV_WITH_DUPLICATES = SYNTHETIC_CSV + \
    "TXN000000001,ACCT00000009,ACCT00000010,BANK0009000,BANK0010000,1.00,2026-09-22 10:30:00,UPI,DUPLICATE,1.1.1.1,Android\n"

# CSV with missing values
SYNTHETIC_CSV_WITH_MISSING = """\
Transaction_ID,Sender_Account,Receiver_Account,Sender_IFSC,Receiver_IFSC,Amount,Timestamp,Payment_Mode,Narration,IP_Address,Device_Type
TXN999000001,ACCT99000001,,BANK9001000,BANK9002000,5000.00,2026-09-22 12:00:00,UPI,MISSING_RECEIVER,192.168.1.1,Android
TXN999000002,ACCT99000002,ACCT99000003,BANK9002000,BANK9003000,,2026-09-22 12:05:00,UPI,MISSING_AMOUNT,192.168.1.2,iOS
"""

# CSV with invalid amounts
SYNTHETIC_CSV_WITH_INVALID_AMOUNTS = """\
Transaction_ID,Sender_Account,Receiver_Account,Sender_IFSC,Receiver_IFSC,Amount,Timestamp,Payment_Mode,Narration,IP_Address,Device_Type
TXN888000001,ACCT88000001,ACCT88000002,BANK8001000,BANK8002000,-500.00,2026-09-22 13:00:00,UPI,NEGATIVE_AMOUNT,192.168.1.1,Android
TXN888000002,ACCT88000003,ACCT88000004,BANK8003000,BANK8004000,0.00,2026-09-22 13:05:00,IMPS,ZERO_AMOUNT,192.168.1.2,iOS
TXN888000003,ACCT88000005,ACCT88000006,BANK8005000,BANK8006000,500.00,2026-09-22 13:10:00,UPI,VALID_AMOUNT,192.168.1.3,Android
"""

# CSV with malformed timestamps
SYNTHETIC_CSV_WITH_BAD_TIMESTAMPS = """\
Transaction_ID,Sender_Account,Receiver_Account,Sender_IFSC,Receiver_IFSC,Amount,Timestamp,Payment_Mode,Narration,IP_Address,Device_Type
TXN777000001,ACCT77000001,ACCT77000002,BANK7001000,BANK7002000,5000.00,NOT-A-TIMESTAMP,UPI,BAD_TS,192.168.1.1,Android
TXN777000002,ACCT77000003,ACCT77000004,BANK7003000,BANK7004000,3000.00,2026-09-22 14:00:00,UPI,GOOD_TS,192.168.1.2,iOS
"""


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_csv_content() -> str:
    """Base synthetic CSV with 7 valid rows."""
    return SYNTHETIC_CSV


@pytest.fixture
def synthetic_df() -> pl.DataFrame:
    """Base synthetic DataFrame (raw, not normalized)."""
    return pl.read_csv(
        io.StringIO(SYNTHETIC_CSV),
        schema_overrides={
            "Transaction_ID": pl.Utf8,
            "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8,
            "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8,
            "Amount": pl.Float64,
            "Timestamp": pl.Utf8,
            "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8,
            "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False,
        infer_schema=False,
    )


@pytest.fixture
def normalized_df(synthetic_df) -> pl.DataFrame:
    """Normalized DataFrame (snake_case, parsed timestamps)."""
    from src.data.ingestion import normalize
    clean_df, _, _ = __import__("src.data.ingestion", fromlist=["validate"]).validate(synthetic_df)
    return normalize(clean_df)


@pytest.fixture
def duckdb_con(normalized_df):
    """In-memory DuckDB connection loaded with synthetic normalized data."""
    from src.data.database import create_in_memory_db_from_df
    return create_in_memory_db_from_df(normalized_df)


@pytest.fixture
def query_module(duckdb_con):
    """
    Returns the query module with its connection monkey-patched
    to use the in-memory test DB.
    """
    import src.data.query as q
    import src.data.database as db

    # Patch the module-level connection
    original_get_connection = db.get_connection
    db._connection = duckdb_con

    yield q

    # Restore
    db._connection = None


@pytest.fixture
def df_with_duplicates() -> pl.DataFrame:
    return pl.read_csv(
        io.StringIO(SYNTHETIC_CSV_WITH_DUPLICATES),
        schema_overrides={
            "Transaction_ID": pl.Utf8, "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8, "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8, "Amount": pl.Float64,
            "Timestamp": pl.Utf8, "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8, "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False, infer_schema=False,
    )


@pytest.fixture
def df_with_missing() -> pl.DataFrame:
    return pl.read_csv(
        io.StringIO(SYNTHETIC_CSV_WITH_MISSING),
        schema_overrides={
            "Transaction_ID": pl.Utf8, "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8, "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8, "Amount": pl.Float64,
            "Timestamp": pl.Utf8, "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8, "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False, infer_schema=False,
        null_values=["", "NULL", "null"],
    )


@pytest.fixture
def df_with_invalid_amounts() -> pl.DataFrame:
    return pl.read_csv(
        io.StringIO(SYNTHETIC_CSV_WITH_INVALID_AMOUNTS),
        schema_overrides={
            "Transaction_ID": pl.Utf8, "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8, "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8, "Amount": pl.Float64,
            "Timestamp": pl.Utf8, "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8, "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False, infer_schema=False,
    )


@pytest.fixture
def df_with_bad_timestamps() -> pl.DataFrame:
    return pl.read_csv(
        io.StringIO(SYNTHETIC_CSV_WITH_BAD_TIMESTAMPS),
        schema_overrides={
            "Transaction_ID": pl.Utf8, "Sender_Account": pl.Utf8,
            "Receiver_Account": pl.Utf8, "Sender_IFSC": pl.Utf8,
            "Receiver_IFSC": pl.Utf8, "Amount": pl.Float64,
            "Timestamp": pl.Utf8, "Payment_Mode": pl.Utf8,
            "Narration": pl.Utf8, "IP_Address": pl.Utf8,
            "Device_Type": pl.Utf8,
        },
        try_parse_dates=False, infer_schema=False,
    )
