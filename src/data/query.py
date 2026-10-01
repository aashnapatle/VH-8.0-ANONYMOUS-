"""
query.py — Public data access layer
=====================================
Aashna → Gunjan & Ananya Contract

This is the ONLY file Gunjan and Ananya need to import.
No knowledge of DuckDB, Parquet, or Polars internals is required.

All functions return typed Python objects (Transaction, AccountSummary, dict).

Usage:
    from src.data.query import (
        get_account_transactions,
        get_incoming_transactions,
        get_outgoing_transactions,
        get_counterparties,
        get_transactions_between,
        get_account_summary,
        get_transaction,
        get_transaction_count,
        get_dataset_stats,
    )

Gunjan example:
    txns = get_account_transactions("KKBK10000000")
    for t in txns:
        # Use t.sender_account, t.receiver_account, t.amount, etc.
        pass

Ananya example:
    summary = get_account_summary("KKBK10000000")
    return summary.as_dict()  # JSON-serializable
"""

import logging
from datetime import datetime
from typing import Optional

import duckdb

from src.data.database import get_connection
from src.data.models import AccountSummary, Transaction

logger = logging.getLogger(__name__)


def _con() -> duckdb.DuckDBPyConnection:
    """Internal shorthand for getting the DB connection."""
    return get_connection()


def _rows_to_transactions(rows: list[tuple], columns: list[str]) -> list[Transaction]:
    """Convert DuckDB result rows to Transaction objects."""
    return [Transaction.from_row(dict(zip(columns, row))) for row in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# Core Query Functions
# ═══════════════════════════════════════════════════════════════════════════════

def get_account_transactions(account_id: str) -> list[Transaction]:
    """
    Return all transactions where account_id is the sender OR receiver.

    Args:
        account_id: Account identifier, e.g. "KKBK10000000"

    Returns:
        List of Transaction objects, ordered by timestamp ascending.
        Returns empty list if account not found.

    Gunjan: use this as the entry point for graph construction around an account.
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE sender_account = ? OR receiver_account = ?
        ORDER BY timestamp ASC
    """
    con = _con()
    result = con.execute(sql, [account_id, account_id])
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    logger.debug(f"get_account_transactions({account_id!r}): {len(rows)} rows")
    return _rows_to_transactions(rows, cols)


def get_incoming_transactions(account_id: str) -> list[Transaction]:
    """
    Return transactions where account_id is the RECEIVER.

    Args:
        account_id: Account identifier

    Returns:
        List of Transaction objects ordered by timestamp ascending.
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE receiver_account = ?
        ORDER BY timestamp ASC
    """
    con = _con()
    result = con.execute(sql, [account_id])
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    logger.debug(f"get_incoming_transactions({account_id!r}): {len(rows)} rows")
    return _rows_to_transactions(rows, cols)


def get_outgoing_transactions(account_id: str) -> list[Transaction]:
    """
    Return transactions where account_id is the SENDER.

    Args:
        account_id: Account identifier

    Returns:
        List of Transaction objects ordered by timestamp ascending.
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE sender_account = ?
        ORDER BY timestamp ASC
    """
    con = _con()
    result = con.execute(sql, [account_id])
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    logger.debug(f"get_outgoing_transactions({account_id!r}): {len(rows)} rows")
    return _rows_to_transactions(rows, cols)


def get_counterparties(account_id: str) -> dict:
    """
    Return all unique counterparty accounts for a given account.

    Returns:
        {
            "account_id": str,
            "senders": list[str],       # accounts that sent TO this account
            "receivers": list[str],     # accounts this account sent TO
            "all_counterparties": list[str]  # union of both
        }
    """
    sql = """
        SELECT
            'sender' AS direction,
            sender_account AS counterparty
        FROM transactions
        WHERE receiver_account = ?
        UNION
        SELECT
            'receiver' AS direction,
            receiver_account AS counterparty
        FROM transactions
        WHERE sender_account = ?
    """
    con = _con()
    result = con.execute(sql, [account_id, account_id])
    rows = result.fetchall()

    senders = sorted({row[1] for row in rows if row[0] == "sender"})
    receivers = sorted({row[1] for row in rows if row[0] == "receiver"})
    all_counterparties = sorted(set(senders) | set(receivers))

    logger.debug(
        f"get_counterparties({account_id!r}): "
        f"{len(senders)} senders, {len(receivers)} receivers"
    )
    return {
        "account_id": account_id,
        "senders": senders,
        "receivers": receivers,
        "all_counterparties": all_counterparties,
    }


def get_transactions_between(
    start_time: str | datetime,
    end_time: str | datetime,
) -> list[Transaction]:
    """
    Return all transactions within a time range (inclusive).

    Args:
        start_time: ISO string "YYYY-MM-DD HH:MM:SS" or datetime object
        end_time: ISO string "YYYY-MM-DD HH:MM:SS" or datetime object

    Returns:
        List of Transaction objects ordered by timestamp ascending.

    Example:
        txns = get_transactions_between("2026-09-22 00:00:00", "2026-09-22 23:59:59")
    """
    if isinstance(start_time, datetime):
        start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(end_time, datetime):
        end_time = end_time.strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """
    con = _con()
    result = con.execute(sql, [start_time, end_time])
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    logger.debug(f"get_transactions_between({start_time!r}, {end_time!r}): {len(rows)} rows")
    return _rows_to_transactions(rows, cols)


def get_account_summary(account_id: str) -> AccountSummary:
    """
    Return aggregated summary metrics for an account.

    Args:
        account_id: Account identifier

    Returns:
        AccountSummary object. Call .as_dict() for JSON output.

    Example:
        summary = get_account_summary("KKBK10000000")
        print(summary.as_dict())
    """
    sql = """
        SELECT
            COUNT(CASE WHEN receiver_account = ? THEN 1 END)         AS incoming_count,
            COUNT(CASE WHEN sender_account = ? THEN 1 END)           AS outgoing_count,
            COALESCE(SUM(CASE WHEN receiver_account = ? THEN amount END), 0) AS total_incoming,
            COALESCE(SUM(CASE WHEN sender_account = ? THEN amount END), 0)   AS total_outgoing,
            COUNT(DISTINCT CASE WHEN receiver_account = ? THEN sender_account END)   AS unique_senders,
            COUNT(DISTINCT CASE WHEN sender_account = ? THEN receiver_account END)   AS unique_receivers,
            MIN(CASE WHEN (sender_account = ? OR receiver_account = ?) THEN timestamp END) AS first_ts,
            MAX(CASE WHEN (sender_account = ? OR receiver_account = ?) THEN timestamp END) AS last_ts
        FROM transactions
        WHERE sender_account = ? OR receiver_account = ?
    """
    params = [account_id] * 12
    con = _con()
    result = con.execute(sql, params)
    row = result.fetchone()

    if row is None or (row[0] == 0 and row[1] == 0):
        # Account not found — return zero summary
        return AccountSummary(
            account_id=account_id,
            incoming_transaction_count=0,
            outgoing_transaction_count=0,
            total_incoming_amount=0.0,
            total_outgoing_amount=0.0,
            unique_incoming_accounts=0,
            unique_outgoing_accounts=0,
            first_transaction_timestamp=None,
            last_transaction_timestamp=None,
        )

    def _parse_ts(ts):
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        try:
            return datetime.fromisoformat(str(ts))
        except Exception:
            return None

    return AccountSummary(
        account_id=account_id,
        incoming_transaction_count=int(row[0] or 0),
        outgoing_transaction_count=int(row[1] or 0),
        total_incoming_amount=float(row[2] or 0.0),
        total_outgoing_amount=float(row[3] or 0.0),
        unique_incoming_accounts=int(row[4] or 0),
        unique_outgoing_accounts=int(row[5] or 0),
        first_transaction_timestamp=_parse_ts(row[6]),
        last_transaction_timestamp=_parse_ts(row[7]),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Query Functions
# ═══════════════════════════════════════════════════════════════════════════════

def get_transaction(transaction_id: str) -> Optional[Transaction]:
    """
    Return a single transaction by its ID.

    Returns:
        Transaction object, or None if not found.
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE transaction_id = ?
        LIMIT 1
    """
    con = _con()
    result = con.execute(sql, [transaction_id])
    cols = [d[0] for d in result.description]
    row = result.fetchone()
    if row is None:
        return None
    return Transaction.from_row(dict(zip(cols, row)))


def get_accounts_by_sender(account_id: str) -> list[str]:
    """
    Return all unique receiver accounts that received money FROM account_id.
    (Which accounts did this account send to?)
    """
    sql = """
        SELECT DISTINCT receiver_account
        FROM transactions
        WHERE sender_account = ?
        ORDER BY receiver_account
    """
    result = _con().execute(sql, [account_id])
    return [row[0] for row in result.fetchall()]


def get_accounts_by_receiver(account_id: str) -> list[str]:
    """
    Return all unique sender accounts that sent money TO account_id.
    (Which accounts sent to this account?)
    """
    sql = """
        SELECT DISTINCT sender_account
        FROM transactions
        WHERE receiver_account = ?
        ORDER BY sender_account
    """
    result = _con().execute(sql, [account_id])
    return [row[0] for row in result.fetchall()]


def get_transaction_count() -> int:
    """Return total number of clean (non-flagged) transactions in the dataset."""
    result = _con().execute("SELECT COUNT(*) FROM transactions")
    return int(result.fetchone()[0])


def get_dataset_stats() -> dict:
    """
    Return high-level statistics about the loaded dataset.
    Useful for Ananya's API health/status endpoint.

    Returns:
        dict with row counts, date range, unique accounts, payment mode breakdown.
    """
    sql = """
        SELECT
            COUNT(*)                        AS total_transactions,
            COUNT(DISTINCT sender_account)  AS unique_senders,
            COUNT(DISTINCT receiver_account) AS unique_receivers,
            MIN(timestamp)                  AS earliest_transaction,
            MAX(timestamp)                  AS latest_transaction,
            SUM(amount)                     AS total_volume,
            AVG(amount)                     AS avg_transaction_amount
        FROM transactions
    """
    result = _con().execute(sql)
    cols = [d[0] for d in result.description]
    row = result.fetchone()
    base = dict(zip(cols, row))

    # Payment mode breakdown
    pm_sql = """
        SELECT payment_mode, COUNT(*) AS count
        FROM transactions
        GROUP BY payment_mode
        ORDER BY count DESC
    """
    pm_result = _con().execute(pm_sql)
    payment_modes = {row[0]: row[1] for row in pm_result.fetchall()}

    # Device type breakdown
    dev_sql = """
        SELECT device_type, COUNT(*) AS count
        FROM transactions
        GROUP BY device_type
        ORDER BY count DESC
    """
    dev_result = _con().execute(dev_sql)
    device_types = {row[0]: row[1] for row in dev_result.fetchall()}

    def _fmt_ts(ts):
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts.isoformat()
        return str(ts)

    return {
        "total_transactions": int(base["total_transactions"] or 0),
        "unique_senders": int(base["unique_senders"] or 0),
        "unique_receivers": int(base["unique_receivers"] or 0),
        "earliest_transaction": _fmt_ts(base["earliest_transaction"]),
        "latest_transaction": _fmt_ts(base["latest_transaction"]),
        "total_volume": float(base["total_volume"] or 0),
        "avg_transaction_amount": round(float(base["avg_transaction_amount"] or 0), 2),
        "payment_mode_breakdown": payment_modes,
        "device_type_breakdown": device_types,
    }


def get_account_transactions_paginated(
    account_id: str,
    limit: int = 1000,
    offset: int = 0,
) -> list[Transaction]:
    """
    Paginated version of get_account_transactions.
    Ananya: use this for large accounts to avoid loading thousands of rows at once.
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE sender_account = ? OR receiver_account = ?
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?
    """
    result = _con().execute(sql, [account_id, account_id, limit, offset])
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    return _rows_to_transactions(rows, cols)


def get_transactions_by_payment_mode(
    account_id: str,
    payment_mode: str,
) -> list[Transaction]:
    """
    Return transactions for an account filtered by payment mode.
    payment_mode: one of IMPS, UPI, RTGS, NEFT
    """
    sql = """
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount, timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE (sender_account = ? OR receiver_account = ?)
          AND payment_mode = ?
        ORDER BY timestamp ASC
    """
    result = _con().execute(sql, [account_id, account_id, payment_mode.upper()])
    cols = [d[0] for d in result.description]
    return _rows_to_transactions(result.fetchall(), cols)


def get_flagged_transactions(account_id: Optional[str] = None) -> list[dict]:
    """
    Return flagged (suspicious/duplicate/invalid) transactions.
    Optionally filter by account_id.
    Shreya: use this for the risk signals view.
    """
    con = _con()
    # Check if flagged view exists
    try:
        if account_id:
            sql = """
                SELECT * FROM transactions_flagged
                WHERE sender_account = ? OR receiver_account = ?
                ORDER BY flag_reason
            """
            result = con.execute(sql, [account_id, account_id])
        else:
            sql = "SELECT * FROM transactions_flagged ORDER BY flag_reason"
            result = con.execute(sql)
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row)) for row in result.fetchall()]
    except Exception as e:
        logger.warning(f"Flagged view not available: {e}")
        return []
