"""
investigate.py — Main investigation orchestration endpoint

This is the core endpoint that:
1. Validates account exists
2. Builds subgraph (BFS through DuckDB)
3. Runs detection on all accounts in subgraph
4. Computes risk scores
5. Runs taint analysis
6. Computes freeze priority
7. Builds evidence package
8. Builds timeline
9. Returns full InvestigationResponse

STATUS: IMPLEMENTED
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException

from backend.db import queries as db
from backend.db.loader import get_account_summary_with_layer
from backend.models.schemas import (
    InvestigationResponse, AccountSummary, GraphData
)
from backend.services import graph_builder, detection, risk_engine
from backend.services import taint_engine, freeze_engine
from backend.services import evidence_builder, timeline

router = APIRouter(prefix="/api", tags=["investigation"])


@router.get("/investigate/{account_id}", response_model=InvestigationResponse)
def investigate(account_id: str, max_hops: int = 4):
    """
    Full money-flow investigation starting from victim account.

    Parameters:
        account_id: The victim account to investigate
        max_hops: Maximum traversal depth (default 4, max 4)
    """
    if not account_id or len(account_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid account_id")
    account_id = account_id.strip()
    max_hops = min(max(max_hops, 1), 4)  # clamp 1-4

    if not db.account_exists(account_id):
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found in dataset",
        )

    # 1. Build subgraph (BFS through DuckDB — does NOT load full dataset)
    G, layers = graph_builder.build_graph(account_id, max_hops)

    # 2. Get all transactions for the subgraph
    all_account_ids = list(layers.keys())
    all_txns = db.get_subgraph_transactions(all_account_ids)

    # 3. Run detection for all accounts in subgraph
    all_account_signals = {}
    for acc_id in all_account_ids:
        acc_txns = [
            t for t in all_txns
            if t["sender_account"] == acc_id or t["receiver_account"] == acc_id
        ]
        signals = detection.run_all_detection(
            G, acc_id, acc_txns, layers, all_txns
        )
        all_account_signals[acc_id] = signals

    # 4. Compute risk scores
    risk_scores = risk_engine.compute_risk_scores_for_subgraph(
        all_account_ids, all_account_signals
    )

    # 5. Taint analysis (from victim account outward)
    taint_results = taint_engine.run_taint_analysis(G, account_id)
    taint_amounts = {k: v.tainted_amount for k, v in taint_results.items()}

    # 6. Freeze priority
    freeze_plan = freeze_engine.compute_freeze_priority(
        G, account_id, taint_results, risk_scores, layers
    )

    # 7. Build evidence package
    evidence = evidence_builder.build_full_evidence_package(
        all_txns, taint_results, risk_scores, freeze_plan, account_id, layers
    )

    # 8. Build timeline
    tl_events = timeline.build_timeline(all_txns, layers, account_id)

    # 9. Account summary
    acc_summary = get_account_summary_with_layer(account_id, layer="VICTIM")


    # 10. Graph data (with risk and taint annotations)
    graph_data = graph_builder.graph_to_schema(
        G, layers,
        risk_scores={k: v.score for k, v in risk_scores.items()},
        taint_amounts=taint_amounts,
    )

    # 11. Get victim's transactions
    victim_txns = [
        t for t in all_txns
        if t["sender_account"] == account_id or t["receiver_account"] == account_id
    ]
    from backend.models.schemas import Transaction
    victim_tx_models = [Transaction(**t) for t in victim_txns]

    return InvestigationResponse(
        victim_account=account_id,
        investigated_at=datetime.now().isoformat(),
        account=acc_summary,
        risk=risk_scores[account_id],
        graph=graph_data,
        timeline=tl_events,
        transactions=victim_tx_models,
        evidence=evidence,
        taint=taint_results[account_id],
        freeze_plan=freeze_plan,
    )


@router.get("/graph/{account_id}", response_model=GraphData)
def get_graph(account_id: str, max_hops: int = 4):
    """
    Return the money-flow subgraph for an account without full investigation payload.
    Useful for standalone graph rendering.
    """
    if not account_id or len(account_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid account_id")
    account_id = account_id.strip()
    max_hops = min(max(max_hops, 1), 4)

    if not db.account_exists(account_id):
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found in dataset",
        )

    G, layers = graph_builder.build_graph(account_id, max_hops)
    taint_results = taint_engine.run_taint_analysis(G, account_id)
    taint_amounts = {k: v.tainted_amount for k, v in taint_results.items()}

    all_account_ids = list(layers.keys())
    all_txns = db.get_subgraph_transactions(all_account_ids)
    all_account_signals = {}
    for acc_id in all_account_ids:
        acc_txns = [
            t for t in all_txns
            if t["sender_account"] == acc_id or t["receiver_account"] == acc_id
        ]
        all_account_signals[acc_id] = detection.run_all_detection(
            G, acc_id, acc_txns, layers, all_txns
        )
    risk_scores = risk_engine.compute_risk_scores_for_subgraph(
        all_account_ids, all_account_signals
    )

    return graph_builder.graph_to_schema(
        G, layers,
        risk_scores={k: v.score for k, v in risk_scores.items()},
        taint_amounts=taint_amounts,
    )

