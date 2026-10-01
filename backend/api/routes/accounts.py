"""
accounts.py — Account lookup API routes

Routes:
  GET /api/accounts/{account_id}   — Account summary
  GET /api/transactions/{account_id} — All transactions

STATUS: IMPLEMENTED
"""
from fastapi import APIRouter, HTTPException
from backend.db import queries as db
from backend.models.schemas import AccountSummary, Transaction
from typing import List

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts/{account_id}", response_model=AccountSummary)
def get_account(account_id: str):
    """
    Return summary information for an account.
    Computes balance from transaction data.
    """
    # Input validation
    if not account_id or len(account_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid account_id")
    account_id = account_id.strip()

    summary = db.get_account_summary(account_id)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found in dataset",
        )
    return AccountSummary(**summary)


@router.get("/transactions/{account_id}", response_model=List[Transaction])
def get_transactions(account_id: str):
    """
    Return all transactions involving this account (sent or received).
    Results are ordered by timestamp ascending.
    """
    if not account_id or len(account_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid account_id")
    account_id = account_id.strip()

    if not db.account_exists(account_id):
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found in dataset",
        )

    txs = db.get_account_transactions(account_id)
    return [Transaction(**t) for t in txs]
