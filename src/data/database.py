"""
database.py — DuckDB connection and schema management
=======================================================
Aashna — Data Engineering & Performance Owner

Manages a persistent DuckDB database backed by Parquet files.
All SQL is executed internally — callers use query.py and never touch DuckDB directly.

Usage:
    from src.data.database import get_connection, initialize_database
    con = get_connection()  # returns initialized DuckDB connection
"""

import logging
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
PROCESSED_DIR = Path(__file__).parent.parent.parent / "data" / "processed"
DUCKDB_PATH = PROCESSED_DIR / "abhedya.duckdb"
CLEAN_PARQUET = PROCESSED_DIR / "transactions.parquet"
FLAGGED_PARQUET = PROCESSED_DIR / "transactions_flagged.parquet"

# Module-level connection cache (singleton per process)
_connection: Optional[duckdb.DuckDBPyConnection] = None


def get_connection(db_path: Optional[Path] = None) -> duckdb.DuckDBPyConnection:
    """
    Return the DuckDB connection (singleton). Creates and initializes if needed.

    Args:
        db_path: Override DB path (useful for in-memory testing: ':memory:')
    """
    global _connection
    if _connection is not None:
        return _connection

    path = db_path or DUCKDB_PATH
    _connection = _create_connection(path)
    return _connection


def _create_connection(db_path) -> duckdb.DuckDBPyConnection:
    """Create and return a new initialized DuckDB connection."""
    path_str = str(db_path) if db_path != ":memory:" else ":memory:"
    logger.info(f"Opening DuckDB: {path_str}")

    con = duckdb.connect(path_str)
    _configure(con)
    _register_views(con, db_path)
    return con


def _configure(con: duckdb.DuckDBPyConnection) -> None:
    """Apply DuckDB performance settings."""
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='2GB'")
    # Enable predicate pushdown for Parquet scans
    con.execute("SET enable_progress_bar=false")


def _register_views(con: duckdb.DuckDBPyConnection, db_path) -> None:
    """
    Register Parquet files as DuckDB views/tables.
    Uses read_parquet with predicate pushdown for performance.
    """
    if not CLEAN_PARQUET.exists():
        logger.warning(
            f"Clean Parquet not found: {CLEAN_PARQUET}. "
            "Run scripts/run_pipeline.py first."
        )
        return

    parquet_path = str(CLEAN_PARQUET).replace("\\", "/")
    flagged_path = str(FLAGGED_PARQUET).replace("\\", "/")

    # Register main transactions view (zero-copy over Parquet)
    con.execute(f"""
        CREATE OR REPLACE VIEW transactions AS
        SELECT * FROM read_parquet('{parquet_path}')
    """)
    logger.info("Registered view: transactions")

    # Register flagged transactions view
    if FLAGGED_PARQUET.exists():
        con.execute(f"""
            CREATE OR REPLACE VIEW transactions_flagged AS
            SELECT * FROM read_parquet('{flagged_path}')
        """)
        logger.info("Registered view: transactions_flagged")

    # Create indexes via a materialized table for hot-path queries
    # DuckDB doesn't have traditional indexes but we can create a
    # materialized table for repeated queries if needed
    logger.info("Views registered successfully")


def initialize_database(db_path: Optional[Path] = None) -> duckdb.DuckDBPyConnection:
    """
    Initialize (or reinitialize) the database from Parquet files.
    Call this after running the ingestion pipeline.

    Returns the initialized connection.
    """
    global _connection
    # Close existing connection if any
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None

    path = db_path or DUCKDB_PATH
    _connection = _create_connection(path)
    logger.info("Database initialized")
    return _connection


def close_connection() -> None:
    """Explicitly close the DuckDB connection."""
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None
        logger.info("DuckDB connection closed")


def reset_connection() -> None:
    """Reset connection (used in tests to get a fresh in-memory DB)."""
    global _connection
    _connection = None


def create_in_memory_db_from_parquet(parquet_path: Path) -> duckdb.DuckDBPyConnection:
    """
    Create an isolated in-memory DuckDB connection from a given Parquet file.
    Used for unit tests — does not affect the module-level singleton.
    """
    con = duckdb.connect(":memory:")
    _configure(con)
    path_str = str(parquet_path).replace("\\", "/")
    con.execute(f"""
        CREATE OR REPLACE VIEW transactions AS
        SELECT * FROM read_parquet('{path_str}')
    """)
    return con


def create_in_memory_db_from_df(df) -> duckdb.DuckDBPyConnection:
    """
    Create an isolated in-memory DuckDB connection from a Polars DataFrame.
    Used for unit tests — does not affect the module-level singleton.
    df: polars.DataFrame
    """
    import polars as pl
    con = duckdb.connect(":memory:")
    _configure(con)
    # Register via Arrow
    arrow_table = df.to_arrow()
    con.register("transactions", arrow_table)
    return con
