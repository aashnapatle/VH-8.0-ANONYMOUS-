"""
timeline.py — Chronological investigation timeline builder

Timeline events come ONLY from verified transaction data.
No LLM-generated events are ever included in the timeline.

STATUS: IMPLEMENTED
"""
from typing import Dict, List, Any
from datetime import datetime

from backend.models.schemas import TimelineEvent


def _parse_ts(ts_str: Any) -> str:
    """Normalize timestamp to ISO string."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts_str).replace(" ", "T"))
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return str(ts_str)


def _hop_to_label(hop: int) -> str:
    labels = {0: "VICTIM", 1: "L1", 2: "L2", 3: "L3"}
    return labels.get(hop, "L3+")


def build_timeline(
    transactions: List[Dict[str, Any]],
    layers: Dict[str, int],
    victim_account: str,
) -> List[TimelineEvent]:
    """
    Build a chronological timeline from verified transaction records.

    Each event describes a money movement with readable description.
    Events are sorted by timestamp ascending.

    Example output:
      10:01 VICTIM ACC_V001 → L1 ACC_L1A  ₹50,000  [UPI, TX001]
      10:05 L1 ACC_L1A → L2 ACC_L2A  ₹25,000  [UPI, TX003]
    """
    events: List[TimelineEvent] = []

    for tx in transactions:
        sender = tx["sender_account"]
        receiver = tx["receiver_account"]
        amount = float(tx["amount"])
        ts = str(tx["timestamp"])
        txn_id = tx["transaction_id"]
        mode = tx.get("payment_mode", "")

        sender_label = _hop_to_label(layers.get(sender, 99))
        receiver_label = _hop_to_label(layers.get(receiver, 99))

        description = (
            f"{sender_label} {sender} → {receiver_label} {receiver}  "
            f"₹{amount:,.0f}"
        )
        if mode:
            description += f"  [{mode}, {txn_id}]"

        events.append(TimelineEvent(
            timestamp=ts,
            event_type="TRANSFER",
            description=description,
            account_from=sender,
            account_to=receiver,
            amount=amount,
            transaction_id=txn_id,
        ))

    # Sort chronologically
    def sort_key(e: TimelineEvent) -> str:
        return e.timestamp or ""

    events.sort(key=sort_key)
    return events
