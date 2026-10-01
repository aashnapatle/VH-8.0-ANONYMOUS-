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
from backend.config import DUCKDB_PATH, SYNTHETIC_CSV, DATA_DIR

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
    conn = duckdb.connect(str(DUCKDB_PATH))
    _create_schema(conn)
    _ensure_data(conn)
    return conn


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
    """Load synthetic CSV if table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if count == 0:
        if SYNTHETIC_CSV.exists():
            logger.info(f"Loading synthetic data from {SYNTHETIC_CSV}")
            load_csv(conn, SYNTHETIC_CSV)
        else:
            logger.warning(
                "No data loaded. Place a CSV at data/synthetic/transactions.csv "
                "or call load_csv() / load_parquet() manually."
            )
    else:
        logger.info(f"DuckDB has {count} transactions loaded.")


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


def reset_and_reload(csv_path: Path | None = None) -> None:
    """
    Drop and recreate the table, reload from CSV.
    Use for fresh ingestion during development.
    """
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS transactions")
    _create_schema(conn)
    if csv_path:
        load_csv(conn, csv_path)
    elif SYNTHETIC_CSV.exists():
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

