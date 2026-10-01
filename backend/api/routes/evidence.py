"""
evidence.py — Evidence endpoint

STATUS: IMPLEMENTED
"""
from fastapi import APIRouter, HTTPException
from typing import List
from backend.models.schemas import EvidenceItem
from backend.api.routes.investigate import investigate as _investigate

router = APIRouter(prefix="/api", tags=["evidence"])


@router.get("/evidence/{account_id}", response_model=List[EvidenceItem])
def get_evidence(account_id: str):
    """
    Return the full evidence package for an account investigation.
    This triggers a full investigation and returns only the evidence list.
    """
    result = _investigate(account_id)
    return result.evidence
