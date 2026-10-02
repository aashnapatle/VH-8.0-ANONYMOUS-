"""
judge.py — Judge Mode / Demo flow endpoints

Provides:
  GET /api/judge/demo  — One-click Judge Mode demo on ground-truth local dataset
  GET /api/benchmark   — Real dataset benchmark measurements
  GET /api/accounts    — List all accounts (for exploration)

STATUS: IMPLEMENTED
"""
import time
from typing import Optional
from fastapi import APIRouter, HTTPException
from backend.db import queries as db
from backend.api.routes.investigate import investigate as _investigate

router = APIRouter(prefix="/api", tags=["judge"])

# Default high-activity real accounts from the supplied 2M dataset
DEFAULT_REAL_VICTIM = "SBIN10012624"
FALLBACK_REAL_VICTIM = "KKBK10013350"


@router.get("/judge/demo")
def judge_demo(account_id: Optional[str] = None):
    """
    One-click Judge Mode demo using the local supplied dataset.
    Runs a full money-flow investigation on a real local account.
    Returns complete investigation + timing information.
    """
    target_account = account_id.strip() if account_id else None

    if not target_account or not db.account_exists(target_account):
        for candidate in [DEFAULT_REAL_VICTIM, FALLBACK_REAL_VICTIM, "ACC_V001"]:
            if db.account_exists(candidate):
                target_account = candidate
                break

    if not target_account:
        all_accs = db.get_all_account_ids()
        if not all_accs:
            raise HTTPException(
                status_code=500,
                detail="No accounts found in local DuckDB dataset.",
            )
        target_account = all_accs[0]

    start = time.perf_counter()
    result = _investigate(target_account)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "demo_victim": target_account,
        "data_source": {
            "type": "LOCAL_SUPPLIED_DATASET",
            "source_file": "VoidHacks8_MuleAccount_2M_Transactions.csv",
            "dataset_rows": 1997748,
        },
        "data_label": "LOCAL_SUPPLIED_DATASET — Ground Truth Investigation",
        "investigation": result,
        "performance": {
            "investigation_ms": round(elapsed_ms, 1),
            "accounts_discovered": len(result.graph.nodes),
            "transactions_in_subgraph": len(result.graph.edges),
            "evidence_items": len(result.evidence),
            "note": "Measured on local DuckDB 2,000,000 transaction dataset.",
        },
    }


@router.get("/accounts")
def list_accounts():
    """Return all account IDs in the dataset."""
    return {"accounts": db.get_all_account_ids()}


@router.get("/benchmark")
def get_benchmark(account_id: Optional[str] = None):
    """
    Return measured benchmark information on real local dataset.
    """
    target = account_id.strip() if account_id else None
    if not target or not db.account_exists(target):
        for candidate in [DEFAULT_REAL_VICTIM, FALLBACK_REAL_VICTIM, "ACC_V001"]:
            if db.account_exists(candidate):
                target = candidate
                break

    if not target:
        all_accs = db.get_all_account_ids()
        if not all_accs:
            raise HTTPException(
                status_code=500,
                detail="No accounts found in local DuckDB dataset.",
            )
        target = all_accs[0]
    
    start = time.perf_counter()
    result = _investigate(target)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "measured": {
            "real_dataset_investigation_ms": round(elapsed_ms, 1),
            "account_investigated": target,
            "accounts_in_subgraph": len(result.graph.nodes),
            "transactions_in_subgraph": len(result.graph.edges),
            "evidence_items": len(result.evidence),
            "total_dataset_rows": 1997748,
        },
        "targets": {
            "victim_query_ms": 2000,
            "ingestion_2m_rows_seconds": 60,
        },
        "data_label": "LOCAL_SUPPLIED_DATASET — Measured Benchmark",
    }
