"""
ai_narrative.py — AI narrative generation endpoint

SECURITY: raw narration is never forwarded to the LLM.
Validation is applied to AI output before returning.

STATUS: IMPLEMENTED
"""
import asyncio
from fastapi import APIRouter, HTTPException
from backend.api.routes.investigate import investigate as _investigate
from backend.services.ai_service import generate_narrative
from backend.services.ai_validator import validate_narrative, build_validator_sets
from backend.config import AI_MAX_RETRIES

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/ai/narrative/{account_id}")
async def ai_narrative(account_id: str):
    """
    Generate an AI narrative for an investigation.
    Validates output before returning.
    Returns: {narrative, validated, issues, injection_test}
    """
    result = _investigate(account_id)

    # Build validator sets from verified data
    known_accounts, known_amounts, known_txn_ids = build_validator_sets(result)


    narrative = ""
    validated = False
    issues = []

    for attempt in range(AI_MAX_RETRIES + 1):
        narrative = await generate_narrative(result, from_validator=(attempt > 0))
        is_valid, issues = validate_narrative(
            narrative, known_accounts, known_amounts, known_txn_ids
        )
        if is_valid:
            validated = True
            break

    # Import injection test for demo
    from backend.services.ai_validator import test_injection_resistance
    injection_test = test_injection_resistance()

    return {
        "account_id": account_id,
        "narrative": narrative,
        "validated": validated,
        "validation_issues": issues if not validated else [],
        "attempts": attempt + 1,
        "injection_resistance_demo": injection_test,
    }
