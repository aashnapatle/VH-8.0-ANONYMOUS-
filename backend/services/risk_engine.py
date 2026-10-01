"""
risk_engine.py — Explainable Mule Risk Index (0–100)

FORMULA (documented — never hidden):
  score = Σ ( RISK_WEIGHTS[signal.code] * signal_triggered )
  capped at 100

All weights are defined in backend/config.py.
Every score is accompanied by reason codes and detail strings.

IMPORTANT DISCLAIMER:
  Risk score is an analytical investigative signal.
  It is NOT proof of criminal activity.
  Authorized human review is always required.

STATUS: IMPLEMENTED
"""
import logging
from typing import Dict, List

from backend.config import RISK_WEIGHTS, RISK_LABELS
from backend.models.schemas import DetectionSignal, RiskScore, RiskReason

logger = logging.getLogger(__name__)


def _risk_label(score: float) -> str:
    """Map numeric score to label using thresholds from config."""
    if score >= RISK_LABELS["CRITICAL"]:
        return "CRITICAL"
    if score >= RISK_LABELS["HIGH"]:
        return "HIGH"
    if score >= RISK_LABELS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def compute_risk_score(
    account_id: str,
    signals: List[DetectionSignal],
) -> RiskScore:
    """
    Compute the Mule Risk Index for one account.

    For each triggered signal, its weight from RISK_WEIGHTS is added.
    Total is capped at 100.

    Returns a RiskScore with full reason codes.
    """
    total_score = 0.0
    reasons: List[RiskReason] = []

    for signal in signals:
        weight = RISK_WEIGHTS.get(signal.code, 0)

        if signal.triggered and weight > 0:
            total_score += weight
            reasons.append(RiskReason(
                code=signal.code,
                detail=signal.detail,
                weight=weight,
            ))

    # Cap at 100
    final_score = min(total_score, 100.0)
    label = _risk_label(final_score)

    logger.info(
        f"Risk score for {account_id}: {final_score:.1f} ({label}) "
        f"— {len(reasons)} reason(s)"
    )

    return RiskScore(
        account_id=account_id,
        score=round(final_score, 1),
        label=label,
        reasons=reasons,
    )


def compute_risk_scores_for_subgraph(
    account_ids: List[str],
    signals_map: Dict[str, List[DetectionSignal]],
) -> Dict[str, RiskScore]:
    """
    Compute risk scores for all accounts in a subgraph.

    Args:
        account_ids: List of account IDs to score
        signals_map: {account_id: [DetectionSignal, ...]}

    Returns:
        {account_id: RiskScore}
    """
    return {
        acc_id: compute_risk_score(acc_id, signals_map.get(acc_id, []))
        for acc_id in account_ids
    }
