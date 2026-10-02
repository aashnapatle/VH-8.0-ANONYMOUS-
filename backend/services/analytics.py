"""
analytics.py — Traceable metadata and money-trail analytics

Builds deterministic, evidence-backed summaries for:
- Transaction chains (multi-hop money trails)
- Payment mode distributions
- IP address reuse & geolocation status
- Device reuse
- Cross-bank movements
- Cycle analysis

STATUS: IMPLEMENTED
"""
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict
from backend.models.schemas import (
    TransactionChainItem,
    PaymentModeSummary,
    IPAnalysis,
    DeviceAnalysis,
    CrossBankAnalysis,
    CycleAnalysis,
    TaintResult,
)


def _ifsc_to_bank(ifsc: Optional[str]) -> str:
    if not ifsc or len(ifsc) < 4:
        return "UNKNOWN"
    return ifsc[:4].upper()


def build_transaction_chain(
    all_txns: List[Dict[str, Any]],
    layers: Dict[str, int],
    taint_results: Dict[str, TaintResult],
    victim_account: str,
) -> List[TransactionChainItem]:
    """
    Build a structured, chronological chain of all transactions in the money-trail.
    Shows the exact next-account and hop level for every movement.
    """
    chain: List[TransactionChainItem] = []

    # Sort transactions chronologically
    sorted_txns = sorted(all_txns, key=lambda t: (str(t.get("timestamp", "")), str(t.get("transaction_id", ""))))

    for tx in sorted_txns:
        s = tx["sender_account"]
        r = tx["receiver_account"]
        amt = float(tx.get("amount", 0))
        tid = str(tx.get("transaction_id", ""))
        ts = str(tx.get("timestamp", ""))
        mode = tx.get("payment_mode")
        s_ifsc = tx.get("sender_ifsc")
        r_ifsc = tx.get("receiver_ifsc")

        # Determine hop level
        r_hop = layers.get(r, layers.get(s, 0) + 1)
        if s == victim_account:
            hop = 1
        else:
            hop = r_hop

        tr = taint_results.get(s)
        ratio = tr.taint_ratio if tr else 0.0
        tainted_amt = round(amt * float(ratio), 2)

        chain.append(TransactionChainItem(
            hop=hop,
            from_account=s,
            to_account=r,
            transaction_id=tid,
            amount=amt,
            tainted_amount=tainted_amt,
            timestamp=ts,
            payment_mode=mode,
            sender_ifsc=s_ifsc,
            receiver_ifsc=r_ifsc,
        ))

    return chain


def build_payment_mode_summary(all_txns: List[Dict[str, Any]]) -> List[PaymentModeSummary]:
    """Summarize transaction counts and total volume by payment mode."""
    counts: Dict[str, int] = defaultdict(int)
    volumes: Dict[str, float] = defaultdict(float)

    for tx in all_txns:
        mode = tx.get("payment_mode") or "UNKNOWN"
        counts[mode] += 1
        volumes[mode] += float(tx.get("amount", 0))

    summaries: List[PaymentModeSummary] = []
    for mode in sorted(counts.keys()):
        summaries.append(PaymentModeSummary(
            payment_mode=mode,
            transaction_count=counts[mode],
            total_amount=round(volumes[mode], 2),
        ))

    return summaries


def build_ip_analysis(
    all_txns: List[Dict[str, Any]],
    ip_to_accounts: Dict[str, Set[str]],
) -> IPAnalysis:
    """Analyze IP address usage and multi-account reuse."""
    all_ips = set(tx.get("ip_address") for tx in all_txns if tx.get("ip_address"))
    reused_details: List[Dict[str, Any]] = []

    for ip in sorted(all_ips):
        accs = sorted(list(ip_to_accounts.get(ip, set())))
        if len(accs) > 1:
            reused_details.append({
                "ip_address": ip,
                "shared_account_count": len(accs),
                "accounts": accs[:10],  # sample accounts
            })

    return IPAnalysis(
        unique_ips=len(all_ips),
        reused_ips_count=len(reused_details),
        ip_country="UNAVAILABLE",
        details=reused_details,
        note="Country geolocation is UNAVAILABLE_FROM_DATASET in local records.",
    )


def build_device_analysis(
    all_txns: List[Dict[str, Any]],
    device_to_accounts: Dict[str, Set[str]],
) -> DeviceAnalysis:
    """Analyze device types and multi-account sharing."""
    all_devices = set(tx.get("device_type") for tx in all_txns if tx.get("device_type"))
    reused_details: List[Dict[str, Any]] = []

    for dev in sorted(all_devices):
        accs = sorted(list(device_to_accounts.get(dev, set())))
        reused_details.append({
            "device_type": dev,
            "account_count": len(accs),
            "sample_accounts": accs[:10],
        })

    return DeviceAnalysis(
        unique_devices=len(all_devices),
        reused_devices_count=len([d for d in reused_details if d["account_count"] > 1]),
        details=reused_details,
    )


def build_cross_bank_analysis(all_txns: List[Dict[str, Any]]) -> CrossBankAnalysis:
    """Analyze cross-bank vs intra-bank transactions."""
    banks: Set[str] = set()
    cross_bank_count = 0
    details: List[Dict[str, Any]] = []

    for tx in all_txns:
        s_bank = _ifsc_to_bank(tx.get("sender_ifsc"))
        r_bank = _ifsc_to_bank(tx.get("receiver_ifsc"))
        if s_bank != "UNKNOWN":
            banks.add(s_bank)
        if r_bank != "UNKNOWN":
            banks.add(r_bank)

        if s_bank != "UNKNOWN" and r_bank != "UNKNOWN" and s_bank != r_bank:
            cross_bank_count += 1
            if len(details) < 20:  # store top 20 sample transitions
                details.append({
                    "transaction_id": tx.get("transaction_id"),
                    "sender_bank": s_bank,
                    "receiver_bank": r_bank,
                    "amount": float(tx.get("amount", 0)),
                })

    return CrossBankAnalysis(
        unique_banks=len(banks),
        banks=sorted(list(banks)),
        cross_bank_transfers_count=cross_bank_count,
        details=details,
    )


def build_cycle_analysis(cycles: List[List[str]]) -> CycleAnalysis:
    """Format detected cycles."""
    return CycleAnalysis(
        cycle_detected=len(cycles) > 0,
        cycle_count=len(cycles),
        cycles_found=cycles[:10],  # return up to 10 cycles
    )
