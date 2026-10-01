"""
evidence_builder.py — Structured evidence package builder

Every piece of evidence is traceable to a source transaction or
a specific analytic result. No LLM-generated claims appear here.

Evidence chain:
  raw DB record → analytic result → evidence item → report

STATUS: IMPLEMENTED
"""
from typing import Dict, List, Any, Optional
from backend.models.schemas import (
    EvidenceItem, Transaction, TaintResult, RiskScore, FreezePlan
)


def build_transaction_evidence(
    transactions: List[Dict[str, Any]],
    taint_results: Dict[str, TaintResult],
    victim_account: str,
    layers: Dict[str, int],
) -> List[EvidenceItem]:
    """
    Build evidence items from transaction data.
    Each transaction that involves tainted money is an evidence item.
    """
    items: List[EvidenceItem] = []

    for tx in transactions:
        sender = tx["sender_account"]
        receiver = tx["receiver_account"]
        amount = float(tx["amount"])

        # Determine relationship
        sender_hop = layers.get(sender, 99)
        receiver_hop = layers.get(receiver, 99)
        sender_label = _hop_to_label(sender_hop)
        receiver_label = _hop_to_label(receiver_hop)
        relationship = f"{sender_label} → {receiver_label}"

        # Get tainted amount flowing through this transaction
        taint = taint_results.get(sender)
        taint_ratio = taint.taint_ratio if taint else 0.0
        tainted_amount = amount * taint_ratio

        rule = "VICTIM_ORIGIN_TRANSFER" if sender == victim_account else "DOWNSTREAM_TRANSFER"

        items.append(EvidenceItem(
            evidence_type="transaction",
            transaction_id=tx["transaction_id"],
            sender=sender,
            receiver=receiver,
            amount=amount,
            tainted_amount=round(tainted_amount, 2),
            timestamp=str(tx["timestamp"]),
            ifsc_sender=tx.get("sender_ifsc"),
            ifsc_receiver=tx.get("receiver_ifsc"),
            payment_mode=tx.get("payment_mode"),
            rule_triggered=rule,
            graph_relationship=relationship,
            # SECURITY: narration is INTENTIONALLY excluded from evidence
            # narration is untrusted attacker-controlled data
        ))

    return items


def build_risk_evidence(risk_scores: Dict[str, RiskScore]) -> List[EvidenceItem]:
    """Build evidence items from risk analysis results."""
    items: List[EvidenceItem] = []
    for account_id, risk in risk_scores.items():
        for reason in risk.reasons:
            items.append(EvidenceItem(
                evidence_type="risk_reason",
                sender=account_id,
                rule_triggered=reason.code,
                detail=(
                    f"Account {account_id} risk={risk.score} ({risk.label}): "
                    f"{reason.code} — {reason.detail} (weight={reason.weight})"
                ),
            ))
    return items


def build_taint_evidence(taint_results: Dict[str, TaintResult]) -> List[EvidenceItem]:
    """Build evidence items from taint analysis."""
    items: List[EvidenceItem] = []
    for account_id, taint in taint_results.items():
        if taint.tainted_amount > 0:
            items.append(EvidenceItem(
                evidence_type="taint",
                sender=account_id,
                amount=taint.total_balance,
                tainted_amount=taint.tainted_amount,
                detail=(
                    f"Account {account_id}: ₹{taint.tainted_amount:,.2f} estimated "
                    f"victim-origin money out of ₹{taint.total_balance:,.2f} total "
                    f"({taint.taint_ratio:.1%} taint ratio). "
                    f"Model: {taint.model_used}"
                ),
                rule_triggered="TAINT_PROPORTIONAL_MODEL",
            ))
    return items


def build_freeze_evidence(freeze_plan: FreezePlan) -> List[EvidenceItem]:
    """Build evidence items from freeze priority analysis."""
    items: List[EvidenceItem] = []
    for candidate in freeze_plan.freeze_candidates:
        items.append(EvidenceItem(
            evidence_type="freeze_priority",
            sender=candidate.account_id,
            amount=candidate.tainted_amount_held,
            tainted_amount=candidate.tainted_amount_held,
            detail=(
                f"Freeze rank #{candidate.rank}: {candidate.account_id} "
                f"({candidate.bank}, {candidate.layer}) — {candidate.reason} "
                f"Risk: {candidate.risk_score}"
            ),
            rule_triggered="FREEZE_PRIORITY_COMPUTED",
        ))
    return items


def build_full_evidence_package(
    transactions: List[Dict[str, Any]],
    taint_results: Dict[str, TaintResult],
    risk_scores: Dict[str, RiskScore],
    freeze_plan: FreezePlan,
    victim_account: str,
    layers: Dict[str, int],
) -> List[EvidenceItem]:
    """
    Assemble the complete evidence package.
    Order: transactions → taint → risk → freeze
    """
    evidence: List[EvidenceItem] = []
    evidence.extend(build_transaction_evidence(
        transactions, taint_results, victim_account, layers
    ))
    evidence.extend(build_taint_evidence(taint_results))
    evidence.extend(build_risk_evidence(risk_scores))
    evidence.extend(build_freeze_evidence(freeze_plan))
    return evidence


def _hop_to_label(hop: int) -> str:
    labels = {0: "VICTIM", 1: "L1", 2: "L2", 3: "L3"}
    return labels.get(hop, "L3+")
