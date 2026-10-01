"""
ai_service.py — Local AI narrative generation (Ollama integration)

SECURITY DESIGN:
  - Raw transaction narration is NEVER sent to the LLM
  - Only structured verified facts are sent as prompt context
  - The LLM generates narrative prose only — it does NOT compute
    risk scores, freeze plans, or legal conclusions
  - Output is validated by ai_validator.py before use
  - If Ollama is unavailable, a template narrative is returned

FLOW:
  Structured evidence JSON (no raw narration)
        ↓
  Ollama (local model, narrative only)
        ↓
  ai_validator.py (verify all amounts/accounts/IDs against DB)
        ↓
  Accepted or rejected (max 2 retries)

STATUS: IMPLEMENTED (with graceful fallback if Ollama unavailable)
"""
import json
import logging
from typing import Optional

import httpx

from backend.config import OLLAMA_URL, OLLAMA_MODEL, AI_ENABLED, AI_TIMEOUT_SECONDS, AI_MAX_RETRIES
from backend.models.schemas import InvestigationResponse

logger = logging.getLogger(__name__)


NARRATIVE_SYSTEM_PROMPT = """You are an AI assistant that writes factual investigative summaries.

RULES (strictly enforced):
1. Use ONLY the facts provided in the JSON data below. Do NOT invent account numbers, amounts, or transactions.
2. Do NOT declare any account holder guilty or innocent. These are analytical indicators only.
3. Do NOT use any information from outside the provided JSON.
4. Do NOT change any numbers. If an amount appears as 50000, write ₹50,000 exactly.
5. Write in formal, neutral investigative language.
6. If the data is insufficient to make a statement, say so explicitly.

Produce a narrative of 3-5 paragraphs summarizing the money flow investigation.
"""


def _build_safe_context(investigation: InvestigationResponse) -> str:
    """
    Build a structured JSON context for the LLM.
    SECURITY: Raw narration is intentionally EXCLUDED.
    """
    safe_facts = {
        "victim_account": investigation.victim_account,
        "investigated_at": investigation.investigated_at,
        "risk": {
            "account": investigation.risk.account_id,
            "score": investigation.risk.score,
            "label": investigation.risk.label,
            "reasons": [
                {"code": r.code, "detail": r.detail}
                for r in investigation.risk.reasons
            ],
        },
        "taint": {
            "account": investigation.taint.account_id,
            "tainted_amount": investigation.taint.tainted_amount,
            "total_balance": investigation.taint.total_balance,
            "taint_ratio": investigation.taint.taint_ratio,
        },
        "freeze_plan": {
            "total_estimated_recoverable": investigation.freeze_plan.total_estimated_recoverable,
            "top_candidates": [
                {
                    "rank": c.rank,
                    "account_id": c.account_id,
                    "bank": c.bank,
                    "layer": c.layer,
                    "tainted_amount_held": c.tainted_amount_held,
                    "estimated_blocked_amount": c.estimated_blocked_amount,
                }
                for c in investigation.freeze_plan.freeze_candidates[:5]
            ],
        },
        "timeline_summary": [
            {
                "timestamp": e.timestamp,
                "description": e.description,
                "amount": e.amount,
            }
            for e in investigation.timeline[:10]
        ],
        "graph_summary": {
            "total_nodes": len(investigation.graph.nodes),
            "total_edges": len(investigation.graph.edges),
            "layers": list(set(n.layer for n in investigation.graph.nodes)),
        },
    }
    return json.dumps(safe_facts, indent=2)


def _template_narrative(investigation: InvestigationResponse) -> str:
    """
    Fallback template narrative when Ollama is unavailable.
    Uses only verified structured data.
    """
    risk = investigation.risk
    taint = investigation.taint
    freeze = investigation.freeze_plan

    top_freeze = freeze.freeze_candidates[0] if freeze.freeze_candidates else None

    lines = [
        f"INVESTIGATION SUMMARY — {investigation.victim_account}",
        f"Investigated at: {investigation.investigated_at}",
        "",
        f"The investigation traced {len(investigation.transactions)} transactions "
        f"across {len(investigation.graph.nodes)} accounts connected to victim account "
        f"{investigation.victim_account}.",
        "",
        f"Risk analysis of the primary account returned a score of "
        f"{risk.score}/100 ({risk.label}). "
        f"Triggered signals: {', '.join(r.code for r in risk.reasons) or 'none'}.",
        "",
        f"Taint analysis (proportional model) estimates ₹{taint.tainted_amount:,.2f} "
        f"of victim-origin money remains traceable in the network out of "
        f"₹{taint.total_balance:,.2f} total balance.",
        "",
    ]

    if top_freeze:
        lines.append(
            f"Freeze priority analysis recommends freezing account "
            f"{top_freeze.account_id} ({top_freeze.bank}) first, "
            f"which is estimated to block ₹{top_freeze.estimated_blocked_amount:,.2f} "
            f"of victim-origin money. "
            f"Total estimated recoverable: ₹{freeze.total_estimated_recoverable:,.2f}."
        )

    lines += [
        "",
        "DISCLAIMER: This is an analytical decision-support summary. "
        "All findings require authorized human review. "
        "Risk scores are investigative signals, not proof of criminal activity. "
        "Taint amounts are approximate (proportional model).",
        "",
        f"[Generated by template — Ollama AI not available]",
    ]

    return "\n".join(lines)


async def generate_narrative(
    investigation: InvestigationResponse,
    from_validator: bool = False,
) -> str:
    """
    Generate an AI narrative using Ollama.
    Falls back to template if Ollama is unavailable.
    Retries on validation failure (handled by caller).
    """
    if not AI_ENABLED:
        return _template_narrative(investigation)

    safe_context = _build_safe_context(investigation)
    prompt = f"{NARRATIVE_SYSTEM_PROMPT}\n\nDATA:\n{safe_context}"

    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            narrative = data.get("response", "")

            if not narrative.strip():
                logger.warning("Ollama returned empty response. Using template.")
                return _template_narrative(investigation)

            logger.info(f"AI narrative generated ({len(narrative)} chars)")
            return narrative

    except httpx.ConnectError:
        logger.warning("Ollama not available (connection refused). Using template narrative.")
        return _template_narrative(investigation)
    except httpx.TimeoutException:
        logger.warning("Ollama timed out. Using template narrative.")
        return _template_narrative(investigation)
    except Exception as e:
        logger.error(f"AI generation error: {e}. Using template narrative.")
        return _template_narrative(investigation)
