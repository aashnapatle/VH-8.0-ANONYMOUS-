"""
judge.py — Judge Mode / Demo flow endpoints

Provides:
  GET /api/judge/demo  — Pre-loaded demo case with synthetic data
  GET /api/benchmark   — Benchmark info (timings)
  GET /api/accounts    — List all accounts (for exploration)

STATUS: IMPLEMENTED
"""
import time
from fastapi import APIRouter
from backend.db import queries as db
from backend.api.routes.investigate import investigate as _investigate

router = APIRouter(prefix="/api", tags=["judge"])

DEMO_VICTIM_ACCOUNT = "ACC_V001"  # Default synthetic demo victim


@router.get("/judge/demo")
def judge_demo():
    """
    One-click Judge Mode demo.
    Runs a full investigation on the synthetic demo victim account.
    Returns the complete result plus timing information.
    """
    start = time.perf_counter()
    result = _investigate(DEMO_VICTIM_ACCOUNT)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "demo_victim": DEMO_VICTIM_ACCOUNT,
        "data_label": "DEVELOPMENT / SYNTHETIC DATA",
        "investigation": result,
        "performance": {
            "investigation_ms": round(elapsed_ms, 1),
            "note": "Timing measured on synthetic data. Real dataset performance not yet benchmarked.",
        },
    }


@router.get("/accounts")
def list_accounts():
    """Return all account IDs in the dataset."""
    return {"accounts": db.get_all_account_ids()}


@router.get("/benchmark")
def get_benchmark():
    """
    Return benchmark information.
    NOTE: Only measured results are reported. Nothing is invented.
    """
    start = time.perf_counter()
    result = _investigate(DEMO_VICTIM_ACCOUNT)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "measured": {
            "synthetic_investigation_ms": round(elapsed_ms, 1),
            "accounts_in_subgraph": len(result.graph.nodes),
            "transactions_in_subgraph": len(result.graph.edges),
            "evidence_items": len(result.evidence),
        },
        "targets": {
            "victim_query_ms": 2000,
            "ingestion_2m_rows_seconds": 60,
            "note": "Targets from project brief. Not yet measured on 2M row dataset.",
        },
        "data_label": "DEVELOPMENT / SYNTHETIC DATA",
    }
