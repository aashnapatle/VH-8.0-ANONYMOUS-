"""
loader.py — DuckDB data layer for Abhedya-Chakra

Responsibilities:
- Initialize DuckDB (in-file mode for persistence)
- Ingest CSV/Parquet transaction data
- Create indexes for fast account lookups
- Validate and normalize transaction records

Design principle: Parquet/DuckDB layer handles large datasets.
Never load 2M+ rows into NetworkX directly.

STATUS: IMPLEMENTED
"""
import duckdb
import logging
from pathlib import Path
from backend.config import DUCKDB_PATH, REAL_PARQUET, REAL_CSV, SYNTHETIC_CSV, DATA_DIR

logger = logging.getLogger(__name__)

# Global connection (module-level singleton)
_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the DuckDB connection, initializing if needed."""
    global _conn
    if _conn is None:
        _conn = _init_db()
    return _conn


def _init_db() -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB, create tables, load data if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        conn = duckdb.connect(str(DUCKDB_PATH), read_only=False)
        _create_schema(conn)
        _ensure_data(conn)
        return conn
    except duckdb.IOException as e:
        if "used by another process" in str(e) or "Cannot open file" in str(e):
            logger.warning("DuckDB opened by another process, connecting in read_only mode.")
            return duckdb.connect(str(DUCKDB_PATH), read_only=True)
        raise


def _create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the transactions table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id   VARCHAR PRIMARY KEY,
            sender_account   VARCHAR NOT NULL,
            receiver_account VARCHAR NOT NULL,
            sender_ifsc      VARCHAR,
            receiver_ifsc    VARCHAR,
            amount           DOUBLE NOT NULL,
            timestamp        TIMESTAMP NOT NULL,
            payment_mode     VARCHAR,
            narration        VARCHAR,
            ip_address       VARCHAR,
            device_type      VARCHAR
        )
    """)

    # Indexes for fast lookups by account
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sender
        ON transactions (sender_account)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_receiver
        ON transactions (receiver_account)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp
        ON transactions (timestamp)
    """)
    logger.info("DuckDB schema ready.")


def _ensure_data(conn: duckdb.DuckDBPyConnection) -> None:
    """Ensure data is loaded into DuckDB. Prioritizes real local dataset."""
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if count == 0:
        if REAL_PARQUET.exists():
            logger.info(f"Loading real local parquet from {REAL_PARQUET}")
            load_parquet(conn, REAL_PARQUET)
        elif REAL_CSV.exists():
            logger.info(f"Loading real local CSV from {REAL_CSV}")
            load_csv(conn, REAL_CSV)
        else:
            logger.error(
                "CRITICAL: Real dataset not found at "
                f"{REAL_PARQUET} or {REAL_CSV}. "
                "The application will not fall back to synthetic data."
            )
    else:
        logger.info(f"DuckDB ready with {count:,} transactions loaded.")


def load_csv(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Load a CSV file into the transactions table.
    Expected columns: transaction_id, sender_account, receiver_account,
    sender_ifsc, receiver_ifsc, amount, timestamp, payment_mode,
    narration, ip_address, device_type
    Returns number of rows loaded.
    """
    # IMPORTANT: narration is treated as untrusted data throughout the system.
    # It is stored as-is but NEVER forwarded to the LLM.
    conn.execute(f"""
        INSERT OR IGNORE INTO transactions
        SELECT
            CAST(transaction_id AS VARCHAR),
            CAST(sender_account  AS VARCHAR),
            CAST(receiver_account AS VARCHAR),
            CAST(sender_ifsc AS VARCHAR),
            CAST(receiver_ifsc AS VARCHAR),
            CAST(amount AS DOUBLE),
            CAST(timestamp AS TIMESTAMP),
            CAST(payment_mode AS VARCHAR),
            CAST(narration AS VARCHAR),
            CAST(ip_address AS VARCHAR),
            CAST(device_type AS VARCHAR)
        FROM read_csv_auto('{csv_path}', header=True)
    """)
    loaded = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    logger.info(f"Loaded CSV. Total rows now: {loaded}")
    return loaded


def load_parquet(conn: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """
    Load a Parquet file into the transactions table.
    Same schema as CSV. For Aashna's data pipeline output.
    """
    conn.execute(f"""
        INSERT OR IGNORE INTO transactions
        SELECT
            CAST(transaction_id AS VARCHAR),
            CAST(sender_account  AS VARCHAR),
            CAST(receiver_account AS VARCHAR),
            CAST(sender_ifsc AS VARCHAR),
            CAST(receiver_ifsc AS VARCHAR),
            CAST(amount AS DOUBLE),
            CAST(timestamp AS TIMESTAMP),
            CAST(payment_mode AS VARCHAR),
            CAST(narration AS VARCHAR),
            CAST(ip_address AS VARCHAR),
            CAST(device_type AS VARCHAR)
        FROM read_parquet('{parquet_path}')
    """)
    loaded = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    logger.info(f"Loaded Parquet. Total rows now: {loaded}")
    return loaded


def reset_and_reload_parquet(parquet_path: Path | None = None) -> int:
    """
    Drop and recreate table, load from real Parquet.
    """
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS transactions")
    _create_schema(conn)
    target_pq = parquet_path or REAL_PARQUET
    if target_pq.exists():
        return load_parquet(conn, target_pq)
    elif REAL_CSV.exists():
        return load_csv(conn, REAL_CSV)
    raise FileNotFoundError(f"Real dataset not found at {target_pq} or {REAL_CSV}")


def reset_and_reload(csv_path: Path | None = None) -> None:
    """
    Drop and recreate the table, reload from specified CSV or real Parquet default.
    """
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS transactions")
    _create_schema(conn)
    if csv_path:
        load_csv(conn, csv_path)
    elif REAL_PARQUET.exists():
        load_parquet(conn, REAL_PARQUET)
    elif REAL_CSV.exists():
        load_csv(conn, REAL_CSV)
    elif SYNTHETIC_CSV.exists():
        logger.warning("Falling back to synthetic CSV in development reset.")
        load_csv(conn, SYNTHETIC_CSV)


def get_account_summary_with_layer(account_id: str, layer: str = "VICTIM"):
    """
    Return an AccountSummary with layer information populated.
    """
    from backend.db import queries as db_queries
    from backend.models.schemas import AccountSummary

    data = db_queries.get_account_summary(account_id)
    if data:
        return AccountSummary(**data, layer=layer)
    return AccountSummary(
        account_id=account_id,
        total_received=0.0,
        total_sent=0.0,
        net_balance=0.0,
        transaction_count=0,
        layer=layer,
    )

