"""
models.py — Transaction data model
====================================
Aashna — Data Engineering & Performance Owner

This module defines the canonical Transaction representation.
Gunjan consumes this — no knowledge of DuckDB/Parquet internals required.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class Transaction:
    """
    Canonical transaction record.

    Frozen (immutable) and slotted for memory efficiency across 2M+ rows.
    Gunjan: use this type in your graph engine node/edge construction.
    Ananya: serialize via dataclasses.asdict(tx) for JSON API responses.
    """
    transaction_id: str
    sender_account: str
    receiver_account: str
    sender_ifsc: str
    receiver_ifsc: str
    amount: float
    timestamp: datetime
    payment_mode: str
    narration: str
    ip_address: str
    device_type: str

    def as_dict(self) -> dict:
        """Return JSON-serializable dictionary representation."""
        return {
            "transaction_id": self.transaction_id,
            "sender_account": self.sender_account,
            "receiver_account": self.receiver_account,
            "sender_ifsc": self.sender_ifsc,
            "receiver_ifsc": self.receiver_ifsc,
            "amount": self.amount,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "payment_mode": self.payment_mode,
            "narration": self.narration,
            "ip_address": self.ip_address,
            "device_type": self.device_type,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Transaction":
        """
        Construct from a DuckDB row dict.
        Handles both datetime objects and string timestamps.
        """
        ts = row["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            transaction_id=row["transaction_id"],
            sender_account=row["sender_account"],
            receiver_account=row["receiver_account"],
            sender_ifsc=row["sender_ifsc"],
            receiver_ifsc=row["receiver_ifsc"],
            amount=float(row["amount"]),
            timestamp=ts,
            payment_mode=row["payment_mode"],
            narration=row["narration"],
            ip_address=row["ip_address"],
            device_type=row["device_type"],
        )


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """
    Aggregated summary for a single account.
    """
    account_id: str
    incoming_transaction_count: int
    outgoing_transaction_count: int
    total_incoming_amount: float
    total_outgoing_amount: float
    unique_incoming_accounts: int
    unique_outgoing_accounts: int
    first_transaction_timestamp: Optional[datetime]
    last_transaction_timestamp: Optional[datetime]

    def as_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "incoming_transaction_count": self.incoming_transaction_count,
            "outgoing_transaction_count": self.outgoing_transaction_count,
            "total_incoming_amount": self.total_incoming_amount,
            "total_outgoing_amount": self.total_outgoing_amount,
            "unique_incoming_accounts": self.unique_incoming_accounts,
            "unique_outgoing_accounts": self.unique_outgoing_accounts,
            "first_transaction_timestamp": (
                self.first_transaction_timestamp.isoformat()
                if self.first_transaction_timestamp else None
            ),
            "last_transaction_timestamp": (
                self.last_transaction_timestamp.isoformat()
                if self.last_transaction_timestamp else None
            ),
        }
