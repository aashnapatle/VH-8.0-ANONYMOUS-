"""
freeze_engine.py — Freeze Priority Engine

METHOD: Max-flow / Min-cut on tainted-balance graph
============================================================

CONCEPTUAL MODEL:
  - Source: victim account (pumps tainted money)
  - Edges: each transaction carries tainted_amount as capacity
  - Sinks: terminal/cash-out nodes (no outgoing edges)

  The minimum cut = minimum set of accounts/edges whose removal
  blocks the maximum tainted flow from reaching cash-out sinks.

  Translated to freeze priority:
  "Cut" nodes = accounts to freeze first to block maximum victim-origin money.

IMPORTANT DISTINCTIONS:
  Risk Score  ≠  Freeze Priority
  - Risk asks: "How suspicious is this account?"
  - Freeze asks: "Freezing which account blocks the most money right now?"
  Example: A LOW-risk account holding ₹500,000 tainted money may need
  to be frozen BEFORE a HIGH-risk account with ₹1,000 tainted money.

DISCLAIMER:
  This is a decision-support recommendation for authorized investigators.
  The system does NOT execute any actual freeze operation.

STATUS: IMPLEMENTED
"""
import logging
from typing import Dict, List, Optional

import networkx as nx

from backend.models.schemas import FreezeCandidate, FreezePlan, TaintResult, RiskScore
from backend.services.graph_builder import get_terminal_nodes
from backend.config import FREEZE_METHOD

logger = logging.getLogger(__name__)


def _ifsc_for_account(G: nx.DiGraph, account_id: str) -> Optional[str]:
    """Try to find an IFSC associated with this account from edge data."""
    for _, _, data in G.out_edges(account_id, data=True):
        if data.get("sender_ifsc"):
            return data["sender_ifsc"]
    for _, _, data in G.in_edges(account_id, data=True):
        if data.get("receiver_ifsc"):
            return data["receiver_ifsc"]
    return None


def _ifsc_to_bank(ifsc: Optional[str]) -> str:
    if not ifsc or len(ifsc) < 4:
        return "UNKNOWN"
    return ifsc[:4].upper()


def build_flow_graph(
    G: nx.DiGraph,
    taint_results: Dict[str, TaintResult],
) -> nx.DiGraph:
    """
    Build a flow graph where edge capacities = tainted amount on each edge.
    This is the graph on which we run max-flow / min-cut.
    """
    flow_G = nx.DiGraph()

    for node in G.nodes():
        flow_G.add_node(node)

    for src, tgt, data in G.edges(data=True):
        tx_amount = float(data.get("amount", 0))
        src_taint = taint_results.get(src)
        if src_taint and src_taint.total_balance > 0:
            taint_ratio = src_taint.taint_ratio
        else:
            taint_ratio = 0.0

        tainted_capacity = tx_amount * taint_ratio

        # If there's already an edge between these nodes, add capacity
        if flow_G.has_edge(src, tgt):
            flow_G[src][tgt]["capacity"] += tainted_capacity
        else:
            flow_G.add_edge(src, tgt, capacity=tainted_capacity)

    return flow_G


def compute_freeze_priority(
    G: nx.DiGraph,
    victim_account: str,
    taint_results: Dict[str, TaintResult],
    risk_scores: Optional[Dict[str, RiskScore]] = None,
    layers: Optional[Dict[str, int]] = None,
) -> FreezePlan:
    """
    Compute freeze priority using max-flow / min-cut analysis.

    Algorithm:
    1. Build flow graph with tainted capacities
    2. Find terminal (sink) nodes
    3. For each sink, run max-flow from victim → sink
    4. Identify min-cut nodes (accounts to freeze)
    5. Rank by estimated_blocked_amount descending

    If no distinct sinks, fall back to ranking by tainted_amount_held.
    """
    terminals = get_terminal_nodes(G)
    if not terminals:
        # Fall back: no terminal nodes — rank all non-victim accounts by tainted amount
        return _fallback_freeze_plan(
            G, victim_account, taint_results, risk_scores, layers
        )

    flow_G = build_flow_graph(G, taint_results)

    # Add a super-sink connected from all terminal nodes
    # This lets us run a single max-flow computation
    SUPER_SINK = "__SUPER_SINK__"
    flow_G.add_node(SUPER_SINK)
    for terminal in terminals:
        tainted = taint_results.get(terminal)
        capacity = tainted.tainted_amount if tainted else 1e9
        flow_G.add_edge(terminal, SUPER_SINK, capacity=max(capacity, 0.01))

    # Run max-flow from victim to super-sink
    freeze_candidates: List[FreezeCandidate] = []
    already_ranked: set = set()

    try:
        flow_value, flow_dict = nx.maximum_flow(
            flow_G, victim_account, SUPER_SINK, capacity="capacity"
        )
        logger.info(f"Max-flow value: ₹{flow_value:,.2f}")

        # Find min-cut
        cut_value, partition = nx.minimum_cut(
            flow_G, victim_account, SUPER_SINK, capacity="capacity"
        )
        reachable, non_reachable = partition

        # Min-cut edges: edges from reachable set to non-reachable set
        # The source accounts of these edges are our freeze candidates
        rank = 1
        for node in reachable:
            if node == victim_account or node == SUPER_SINK:
                continue
            # Check if this node has outgoing edges to non-reachable set
            cut_outflow = sum(
                flow_G[node][nbr].get("capacity", 0)
                for nbr in G.successors(node)
                if nbr in non_reachable
            )
            if cut_outflow > 0 and node not in already_ranked:
                taint = taint_results.get(node)
                risk = risk_scores.get(node) if risk_scores else None
                ifsc = _ifsc_for_account(G, node)
                layer_label = f"L{layers.get(node, '?')}" if layers else "UNKNOWN"

                freeze_candidates.append(FreezeCandidate(
                    rank=rank,
                    account_id=node,
                    bank=_ifsc_to_bank(ifsc),
                    ifsc=ifsc,
                    layer=layer_label,
                    tainted_amount_held=taint.tainted_amount if taint else 0.0,
                    estimated_blocked_amount=round(cut_outflow, 2),
                    risk_score=risk.score if risk else None,
                    reason=(
                        f"Min-cut node: freezing blocks ₹{cut_outflow:,.0f} "
                        f"of victim-origin money from reaching cash-out"
                    ),
                ))
                already_ranked.add(node)
                rank += 1

    except Exception as e:
        logger.warning(f"Max-flow computation failed ({e}). Using fallback ranking.")
        return _fallback_freeze_plan(
            G, victim_account, taint_results, risk_scores, layers
        )

    if not freeze_candidates:
        return _fallback_freeze_plan(
            G, victim_account, taint_results, risk_scores, layers
        )

    # Sort by estimated_blocked_amount descending, re-rank
    freeze_candidates.sort(key=lambda c: c.estimated_blocked_amount, reverse=True)
    for i, cand in enumerate(freeze_candidates):
        cand.rank = i + 1

    total_recoverable = sum(c.tainted_amount_held for c in freeze_candidates)

    return FreezePlan(
        freeze_candidates=freeze_candidates,
        total_estimated_recoverable=round(total_recoverable, 2),
        method=f"{FREEZE_METHOD}_proportional_taint",
    )


def _fallback_freeze_plan(
    G: nx.DiGraph,
    victim_account: str,
    taint_results: Dict[str, TaintResult],
    risk_scores: Optional[Dict[str, RiskScore]],
    layers: Optional[Dict[str, int]],
) -> FreezePlan:
    """
    Fallback when max-flow cannot run.
    Ranks accounts by tainted_amount_held descending.
    NOTE: This is NOT min-cut. It is a simpler heuristic.
    """
    logger.info("Using fallback freeze ranking (tainted_amount descending).")

    candidates: List[FreezeCandidate] = []
    for node in G.nodes():
        if node == victim_account:
            continue
        taint = taint_results.get(node)
        if not taint or taint.tainted_amount <= 0:
            continue

        risk = risk_scores.get(node) if risk_scores else None
        ifsc = _ifsc_for_account(G, node)
        layer_label = f"L{layers.get(node, '?')}" if layers else "UNKNOWN"

        candidates.append(FreezeCandidate(
            rank=0,
            account_id=node,
            bank=_ifsc_to_bank(ifsc),
            ifsc=ifsc,
            layer=layer_label,
            tainted_amount_held=taint.tainted_amount,
            estimated_blocked_amount=taint.tainted_amount,
            risk_score=risk.score if risk else None,
            reason=(
                f"Fallback ranking: holds ₹{taint.tainted_amount:,.0f} "
                "of estimated victim-origin money"
            ),
        ))

    candidates.sort(key=lambda c: c.estimated_blocked_amount, reverse=True)
    for i, cand in enumerate(candidates):
        cand.rank = i + 1

    total_recoverable = sum(c.tainted_amount_held for c in candidates)

    return FreezePlan(
        freeze_candidates=candidates,
        total_estimated_recoverable=round(total_recoverable, 2),
        method="fallback_tainted_amount_ranking",
    )
