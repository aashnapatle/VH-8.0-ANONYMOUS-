"""
queries.py — Parameterized DuckDB queries

All queries use parameterized inputs to prevent SQL injection.
Never use f-string interpolation for user-supplied account IDs.

STATUS: IMPLEMENTED
"""
from typing import List, Dict, Any, Optional
import duckdb
from backend.db.loader import get_connection


def get_account_transactions(account_id: str) -> List[Dict[str, Any]]:
    """
    Return all transactions where account_id is sender OR receiver.
    Parameterized — safe against SQL injection.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            transaction_id,
            sender_account,
            receiver_account,
            sender_ifsc,
            receiver_ifsc,
            amount,
            CAST(timestamp AS VARCHAR) AS timestamp,
            payment_mode,
            narration,
            ip_address,
            device_type
        FROM transactions
        WHERE sender_account = ?
           OR receiver_account = ?
        ORDER BY timestamp ASC
    """, [account_id, account_id]).fetchall()

    columns = [
        "transaction_id", "sender_account", "receiver_account",
        "sender_ifsc", "receiver_ifsc", "amount", "timestamp",
        "payment_mode", "narration", "ip_address", "device_type"
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_outgoing_transactions(account_id: str) -> List[Dict[str, Any]]:
    """Return transactions where account_id is the sender."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount,
            CAST(timestamp AS VARCHAR) AS timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE sender_account = ?
        ORDER BY timestamp ASC
    """, [account_id]).fetchall()

    columns = [
        "transaction_id", "sender_account", "receiver_account",
        "sender_ifsc", "receiver_ifsc", "amount", "timestamp",
        "payment_mode", "narration", "ip_address", "device_type"
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_incoming_transactions(account_id: str) -> List[Dict[str, Any]]:
    """Return transactions where account_id is the receiver."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount,
            CAST(timestamp AS VARCHAR) AS timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE receiver_account = ?
        ORDER BY timestamp ASC
    """, [account_id]).fetchall()

    columns = [
        "transaction_id", "sender_account", "receiver_account",
        "sender_ifsc", "receiver_ifsc", "amount", "timestamp",
        "payment_mode", "narration", "ip_address", "device_type"
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_account_summary(account_id: str) -> Optional[Dict[str, Any]]:
    """
    Compute account summary from transaction data.
    Returns None if account not found.
    """
    conn = get_connection()
    result = conn.execute("""
        SELECT
            SUM(CASE WHEN receiver_account = ? THEN amount ELSE 0 END) AS total_received,
            SUM(CASE WHEN sender_account   = ? THEN amount ELSE 0 END) AS total_sent,
            COUNT(*) AS transaction_count,
            CAST(MIN(timestamp) AS VARCHAR) AS first_seen,
            CAST(MAX(timestamp) AS VARCHAR) AS last_seen
        FROM transactions
        WHERE sender_account = ? OR receiver_account = ?
    """, [account_id, account_id, account_id, account_id]).fetchone()

    if not result or result[2] == 0:
        return None

    total_received, total_sent, tx_count, first_seen, last_seen = result

    # Collect distinct banks (from IFSCs where this account appears)
    bank_rows = conn.execute("""
        SELECT DISTINCT
            CASE
                WHEN sender_account = ? THEN LEFT(sender_ifsc, 4)
                ELSE LEFT(receiver_ifsc, 4)
            END AS bank_code
        FROM transactions
        WHERE (sender_account = ? OR receiver_account = ?)
          AND (sender_ifsc IS NOT NULL OR receiver_ifsc IS NOT NULL)
    """, [account_id, account_id, account_id]).fetchall()

    banks = [r[0] for r in bank_rows if r[0]]

    return {
        "account_id": account_id,
        "total_received": float(total_received or 0),
        "total_sent": float(total_sent or 0),
        "net_balance": float((total_received or 0) - (total_sent or 0)),
        "transaction_count": int(tx_count),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "banks": banks,
    }


def get_subgraph_transactions(
    account_ids: List[str]
) -> List[Dict[str, Any]]:
    """
    Given a list of account IDs, return all transactions between them.
    Used to build the subgraph for NetworkX (only loads relevant edges).
    """
    if not account_ids:
        return []

    conn = get_connection()
    placeholders = ",".join(["?" for _ in account_ids])
    rows = conn.execute(f"""
        SELECT
            transaction_id, sender_account, receiver_account,
            sender_ifsc, receiver_ifsc, amount,
            CAST(timestamp AS VARCHAR) AS timestamp,
            payment_mode, narration, ip_address, device_type
        FROM transactions
        WHERE sender_account   IN ({placeholders})
           OR receiver_account IN ({placeholders})
        ORDER BY timestamp ASC
    """, account_ids + account_ids).fetchall()

    columns = [
        "transaction_id", "sender_account", "receiver_account",
        "sender_ifsc", "receiver_ifsc", "amount", "timestamp",
        "payment_mode", "narration", "ip_address", "device_type"
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_all_account_ids() -> List[str]:
    """Return all distinct account IDs in the dataset."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT account_id FROM (
            SELECT sender_account   AS account_id FROM transactions
            UNION
            SELECT receiver_account AS account_id FROM transactions
        )
        ORDER BY account_id
    """).fetchall()
    return [r[0] for r in rows]


def account_exists(account_id: str) -> bool:
    """Check if an account exists in the dataset."""
    conn = get_connection()
    result = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE sender_account = ? OR receiver_account = ?
        LIMIT 1
    """, [account_id, account_id]).fetchone()
    return result[0] > 0
