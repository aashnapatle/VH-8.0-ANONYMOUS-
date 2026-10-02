"""
detection.py — Mule behavior detection engine

This module analyses a subgraph and transaction set to detect
patterns associated with mule account behavior.

IMPORTANT DISCLAIMERS (built into code):
- These are investigative signals, NOT proof of criminal activity.
- All thresholds are configurable in config.py and documented.
- Detection ≠ guilt. Every finding requires authorized human review.

Signals detected:
  HIGH_FAN_IN           - Many distinct senders
  HIGH_FAN_OUT          - Many distinct receivers
  RAPID_PASS_THROUGH    - Large fraction of inflow exits quickly
  MULTI_HOP_MOVEMENT    - Account is part of 3+ hop chain
  CYCLE_DETECTED        - Account participates in a fund cycle
  CROSS_BANK_ACTIVITY   - Transactions cross many distinct banks
  DEVICE_OVERLAP        - Device type shared with many accounts
  IP_OVERLAP            - IP address shared with many accounts

STATUS: IMPLEMENTED
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

import networkx as nx

from backend.config import (
    FAN_IN_THRESHOLD, FAN_OUT_THRESHOLD,
    PASS_THROUGH_RATIO, PASS_THROUGH_WINDOW_MINUTES,
    CROSS_BANK_THRESHOLD, CYCLE_DETECTION_ENABLED,
    DEVICE_OVERLAP_THRESHOLD, IP_OVERLAP_THRESHOLD,
)
from backend.models.schemas import DetectionSignal
from backend.services.graph_builder import get_cycles

logger = logging.getLogger(__name__)


def _parse_ts(ts_str: Any) -> Optional[datetime]:
    """Parse timestamp string to datetime. Returns None on failure."""
    if not ts_str:
        return None
    try:
        if isinstance(ts_str, datetime):
            return ts_str
        return datetime.fromisoformat(str(ts_str).replace(" ", "T"))
    except (ValueError, TypeError):
        return None


def _ifsc_to_bank(ifsc: Optional[str]) -> str:
    if not ifsc or len(ifsc) < 4:
        return "UNKNOWN"
    return ifsc[:4].upper()


def detect_fan_in(G: nx.DiGraph, account_id: str) -> DetectionSignal:
    """HIGH_FAN_IN: account receives from many distinct senders."""
    senders = set(src for src, _ in G.in_edges(account_id))
    count = len(senders)
    triggered = count >= FAN_IN_THRESHOLD
    return DetectionSignal(
        code="HIGH_FAN_IN",
        triggered=triggered,
        detail=f"{count} distinct senders (threshold: {FAN_IN_THRESHOLD})",
        value=float(count),
    )


def detect_fan_out(G: nx.DiGraph, account_id: str) -> DetectionSignal:
    """HIGH_FAN_OUT: account sends to many distinct receivers."""
    receivers = set(tgt for _, tgt in G.out_edges(account_id))
    count = len(receivers)
    triggered = count >= FAN_OUT_THRESHOLD
    return DetectionSignal(
        code="HIGH_FAN_OUT",
        triggered=triggered,
        detail=f"{count} distinct receivers (threshold: {FAN_OUT_THRESHOLD})",
        value=float(count),
    )


def detect_rapid_pass_through(
    G: nx.DiGraph,
    account_id: str,
    transactions: List[Dict[str, Any]],
) -> DetectionSignal:
    """
    RAPID_PASS_THROUGH: a large fraction of inflow exits within PASS_THROUGH_WINDOW_MINUTES.

    Method:
    1. Compute total inflow.
    2. For each incoming tx, find outgoing txs within the window.
    3. If rapid_outflow / total_inflow >= PASS_THROUGH_RATIO → triggered.
    """
    window = timedelta(minutes=PASS_THROUGH_WINDOW_MINUTES)

    incoming = [
        t for t in transactions
        if t["receiver_account"] == account_id and t["amount"] > 0
    ]
    outgoing = [
        t for t in transactions
        if t["sender_account"] == account_id and t["amount"] > 0
    ]

    total_inflow = sum(t["amount"] for t in incoming)
    if total_inflow == 0:
        return DetectionSignal(
            code="RAPID_PASS_THROUGH",
            triggered=False,
            detail="No inflow found",
            value=0.0,
        )

    # For each incoming tx, check outgoing within window
    rapid_outflow = 0.0
    for inc in incoming:
        inc_ts = _parse_ts(inc["timestamp"])
        if not inc_ts:
            continue
        for out in outgoing:
            out_ts = _parse_ts(out["timestamp"])
            if not out_ts:
                continue
            if timedelta(0) <= (out_ts - inc_ts) <= window:
                rapid_outflow += out["amount"]

    # Cap rapid_outflow at total_inflow (can't move more than you received)
    rapid_outflow = min(rapid_outflow, total_inflow)
    ratio = rapid_outflow / total_inflow
    triggered = ratio >= PASS_THROUGH_RATIO

    return DetectionSignal(
        code="RAPID_PASS_THROUGH",
        triggered=triggered,
        detail=(
            f"{ratio:.0%} of inflow (₹{rapid_outflow:,.0f} / ₹{total_inflow:,.0f}) "
            f"exited within {PASS_THROUGH_WINDOW_MINUTES} min "
            f"(threshold: {PASS_THROUGH_RATIO:.0%})"
        ),
        value=round(ratio, 4),
    )


def detect_multi_hop(
    layers: Dict[str, int],
    account_id: str,
) -> DetectionSignal:
    """MULTI_HOP_MOVEMENT: account is 2+ hops from victim (part of deep chain)."""
    hop = layers.get(account_id, 0)
    triggered = hop >= 2
    return DetectionSignal(
        code="MULTI_HOP_MOVEMENT",
        triggered=triggered,
        detail=f"Account is at hop {hop} from victim",
        value=float(hop),
    )


def detect_cycle(
    G: nx.DiGraph,
    account_id: str,
    cycles: Optional[List[List[str]]] = None,
) -> DetectionSignal:
    """CYCLE_DETECTED: account participates in any detected fund cycle."""
    if not CYCLE_DETECTION_ENABLED:
        return DetectionSignal(
            code="CYCLE_DETECTED",
            triggered=False,
            detail="Cycle detection disabled in config",
            value=0.0,
        )

    if cycles is None:
        cycles = get_cycles(G)

    account_cycles = [c for c in cycles if account_id in c]
    triggered = len(account_cycles) > 0

    return DetectionSignal(
        code="CYCLE_DETECTED",
        triggered=triggered,
        detail=(
            f"Participates in {len(account_cycles)} cycle(s): "
            + (str(account_cycles[0]) if account_cycles else "none")
        ),
        value=float(len(account_cycles)),
    )


def detect_cross_bank(
    G: nx.DiGraph,
    account_id: str,
    transactions: List[Dict[str, Any]],
) -> DetectionSignal:
    """CROSS_BANK_ACTIVITY: transactions involve many distinct banks."""
    banks: set = set()
    for tx in transactions:
        if tx["sender_account"] == account_id and tx.get("sender_ifsc"):
            banks.add(_ifsc_to_bank(tx["sender_ifsc"]))
        if tx["receiver_account"] == account_id and tx.get("receiver_ifsc"):
            banks.add(_ifsc_to_bank(tx["receiver_ifsc"]))

    count = len(banks)
    triggered = count >= CROSS_BANK_THRESHOLD
    return DetectionSignal(
        code="CROSS_BANK_ACTIVITY",
        triggered=triggered,
        detail=f"Transactions span {count} distinct banks: {', '.join(sorted(banks))}",
        value=float(count),
    )


def build_overlap_indexes(all_transactions: List[Dict[str, Any]]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Precompute device-to-accounts and IP-to-accounts mappings once for O(1) lookups."""
    device_to_accounts: Dict[str, Set[str]] = defaultdict(set)
    ip_to_accounts: Dict[str, Set[str]] = defaultdict(set)
    for tx in all_transactions:
        s = tx.get("sender_account")
        r = tx.get("receiver_account")
        dev = tx.get("device_type")
        ip = tx.get("ip_address")
        if dev:
            if s: device_to_accounts[dev].add(s)
            if r: device_to_accounts[dev].add(r)
        if ip:
            if s: ip_to_accounts[ip].add(s)
            if r: ip_to_accounts[ip].add(r)
    return device_to_accounts, ip_to_accounts


def detect_device_overlap(
    account_id: str,
    transactions: List[Dict[str, Any]],
    all_transactions: Optional[List[Dict[str, Any]]] = None,
    device_to_accounts: Optional[Dict[str, Set[str]]] = None,
) -> DetectionSignal:
    """
    DEVICE_OVERLAP: device types associated with this account
    also appear in many other accounts (coordination signal).
    """
    my_devices: set = set()
    for tx in transactions:
        if tx.get("device_type"):
            my_devices.add(tx["device_type"])

    if not my_devices:
        return DetectionSignal(
            code="DEVICE_OVERLAP",
            triggered=False,
            detail="No device data available",
            value=0.0,
        )

    if device_to_accounts is None and all_transactions is not None:
        device_to_accounts, _ = build_overlap_indexes(all_transactions)

    accounts_with_same_device: set = set()
    if device_to_accounts:
        for dev in my_devices:
            accounts_with_same_device.update(device_to_accounts.get(dev, set()))
        accounts_with_same_device.discard(account_id)

    count = len(accounts_with_same_device)
    triggered = count >= DEVICE_OVERLAP_THRESHOLD

    return DetectionSignal(
        code="DEVICE_OVERLAP",
        triggered=triggered,
        detail=(
            f"Device(s) {my_devices} shared with {count} other accounts "
            f"(threshold: {DEVICE_OVERLAP_THRESHOLD})"
        ),
        value=float(count),
    )


def detect_ip_overlap(
    account_id: str,
    transactions: List[Dict[str, Any]],
    all_transactions: Optional[List[Dict[str, Any]]] = None,
    ip_to_accounts: Optional[Dict[str, Set[str]]] = None,
) -> DetectionSignal:
    """
    IP_OVERLAP: IP addresses associated with this account
    also appear in transactions of many other accounts.
    """
    my_ips: set = set()
    for tx in transactions:
        if tx.get("ip_address"):
            my_ips.add(tx["ip_address"])

    if not my_ips:
        return DetectionSignal(
            code="IP_OVERLAP",
            triggered=False,
            detail="No IP data available",
            value=0.0,
        )

    if ip_to_accounts is None and all_transactions is not None:
        _, ip_to_accounts = build_overlap_indexes(all_transactions)

    accounts_with_same_ip: set = set()
    if ip_to_accounts:
        for ip in my_ips:
            accounts_with_same_ip.update(ip_to_accounts.get(ip, set()))
        accounts_with_same_ip.discard(account_id)

    count = len(accounts_with_same_ip)
    triggered = count >= IP_OVERLAP_THRESHOLD

    return DetectionSignal(
        code="IP_OVERLAP",
        triggered=triggered,
        detail=(
            f"IP(s) {my_ips} shared with {count} other accounts "
            f"(threshold: {IP_OVERLAP_THRESHOLD})"
        ),
        value=float(count),
    )


def run_all_detection(
    G: nx.DiGraph,
    account_id: str,
    transactions: List[Dict[str, Any]],
    layers: Dict[str, int],
    all_transactions: Optional[List[Dict[str, Any]]] = None,
    cycles: Optional[List[List[str]]] = None,
    device_to_accounts: Optional[Dict[str, Set[str]]] = None,
    ip_to_accounts: Optional[Dict[str, Set[str]]] = None,
) -> List[DetectionSignal]:
    """
    Run all detection signals for a given account.
    Returns list of DetectionSignal objects.
    """
    if all_transactions is None:
        all_transactions = transactions

    if cycles is None:
        cycles = get_cycles(G) if CYCLE_DETECTION_ENABLED else []

    signals = [
        detect_fan_in(G, account_id),
        detect_fan_out(G, account_id),
        detect_rapid_pass_through(G, account_id, transactions),
        detect_multi_hop(layers, account_id),
        detect_cycle(G, account_id, cycles),
        detect_cross_bank(G, account_id, transactions),
        detect_device_overlap(account_id, transactions, all_transactions, device_to_accounts=device_to_accounts),
        detect_ip_overlap(account_id, transactions, all_transactions, ip_to_accounts=ip_to_accounts),
    ]

    triggered_codes = [s.code for s in signals if s.triggered]
    logger.info(
        f"Detection for {account_id}: {len(triggered_codes)} signals triggered: "
        f"{triggered_codes}"
    )

    return signals
