"""
taint_engine.py — Victim-origin money taint tracking (Proportional Model)

MODEL: PROPORTIONAL TAINT
================================
Formula:
  taint_ratio     = tainted_balance / total_balance
  tainted_out_tx  = tx_amount * taint_ratio

Example:
  Account balance = ₹100,000
  Tainted balance = ₹40,000
  taint_ratio     = 0.40

  Sends ₹20,000:
  tainted_out     = ₹20,000 * 0.40 = ₹8,000

LIMITATIONS (documented here and in API responses):
- Assumes proportional mixing of funds (like a water-mixing model)
- Requires complete transaction history in the dataset
- Does NOT implement FIFO (first-in-first-out) ordering
- Approximate — not suitable as standalone forensic evidence
- Does not handle missing transactions (incomplete dataset)
- No multi-victim attribution support in v1

DISCLAIMER:
  Taint amounts are investigative approximations only.
  Not suitable for legal conclusions without expert forensic review.

STATUS: IMPLEMENTED
"""
import logging
from typing import Dict, List, Any, Optional

import networkx as nx

from backend.models.schemas import TaintResult

logger = logging.getLogger(__name__)


class ProportionalTaintEngine:
    """
    Propagates victim-origin money taint through a directed transaction graph
    using the proportional model.

    Usage:
        engine = ProportionalTaintEngine(G, victim_account, victim_amount)
        engine.propagate()
        taint = engine.get_taint(account_id)
    """

    def __init__(
        self,
        G: nx.DiGraph,
        victim_account: str,
        victim_tainted_amount: float,
    ):
        self.G = G
        self.victim_account = victim_account

        # State: per account, track total received and tainted received
        self.total_balance: Dict[str, float] = {}
        self.tainted_balance: Dict[str, float] = {}

        # Seed the victim
        self.total_balance[victim_account] = victim_tainted_amount
        self.tainted_balance[victim_account] = victim_tainted_amount

    def propagate(self) -> None:
        """
        Traverse the graph in topological order (following transaction timestamps)
        and propagate taint using the proportional model.

        For cycles: we do one pass and note that cycles require iterative
        convergence (not implemented in v1 — cycles get one pass taint).
        """
        # Use topological sort where possible; fall back to BFS for cyclic graphs
        try:
            node_order = list(nx.topological_sort(self.G))
        except nx.NetworkXUnfeasible:
            # Graph has cycles — fall back to BFS from victim
            logger.warning(
                "Graph has cycles. Using BFS order for taint propagation. "
                "Cycle taint is approximate."
            )
            node_order = list(nx.bfs_tree(self.G, self.victim_account).nodes())
            # Add any remaining nodes
            remaining = set(self.G.nodes()) - set(node_order)
            node_order.extend(remaining)

        for node in node_order:
            if node not in self.total_balance:
                # Initialize from incoming edges
                total_in = sum(
                    data.get("amount", 0)
                    for _, _, data in self.G.in_edges(node, data=True)
                )
                self.total_balance[node] = float(total_in)
                self.tainted_balance[node] = 0.0

            # Process outgoing edges: propagate taint proportionally
            total = self.total_balance.get(node, 0)
            tainted = self.tainted_balance.get(node, 0)

            if total <= 0:
                continue

            taint_ratio = min(tainted / total, 1.0)  # never exceed 1.0

            for _, receiver, data in self.G.out_edges(node, data=True):
                tx_amount = float(data.get("amount", 0))
                if tx_amount <= 0:
                    continue

                tainted_out = tx_amount * taint_ratio

                # Update receiver's balances
                if receiver not in self.total_balance:
                    self.total_balance[receiver] = 0.0
                    self.tainted_balance[receiver] = 0.0

                self.total_balance[receiver] += tx_amount
                self.tainted_balance[receiver] += tainted_out

                logger.debug(
                    f"Taint propagation: {node} → {receiver} "
                    f"tx=₹{tx_amount:,.0f} tainted=₹{tainted_out:,.2f} "
                    f"ratio={taint_ratio:.2%}"
                )

    def get_taint(self, account_id: str) -> TaintResult:
        """Return TaintResult for a specific account."""
        total = self.total_balance.get(account_id, 0.0)
        tainted = self.tainted_balance.get(account_id, 0.0)
        tainted = min(tainted, total)  # sanity cap
        ratio = (tainted / total) if total > 0 else 0.0

        return TaintResult(
            account_id=account_id,
            tainted_amount=round(tainted, 2),
            total_balance=round(total, 2),
            taint_ratio=round(ratio, 4),
        )

    def get_all_taints(self) -> Dict[str, TaintResult]:
        """Return TaintResult for every account in the graph."""
        return {
            node: self.get_taint(node)
            for node in self.G.nodes()
        }

    def get_taint_amounts(self) -> Dict[str, float]:
        """Return just the tainted_amount per account (for graph visualization)."""
        return {
            node: self.get_taint(node).tainted_amount
            for node in self.G.nodes()
        }


def run_taint_analysis(
    G: nx.DiGraph,
    victim_account: str,
    victim_tainted_amount: Optional[float] = None,
) -> Dict[str, TaintResult]:
    """
    Convenience function to run full taint analysis on a subgraph.

    victim_tainted_amount: the amount of victim-origin money entering the graph.
    If None, uses total outflow from victim as seed.
    """
    if victim_tainted_amount is None:
        # Seed with total outflow from victim
        victim_tainted_amount = sum(
            data.get("amount", 0)
            for _, _, data in G.out_edges(victim_account, data=True)
        )

    if victim_tainted_amount <= 0:
        logger.warning(
            f"Victim account {victim_account} has no outgoing transactions. "
            "Taint will be zero everywhere."
        )
        return {
            node: TaintResult(
                account_id=node,
                tainted_amount=0.0,
                total_balance=0.0,
                taint_ratio=0.0,
            )
            for node in G.nodes()
        }

    engine = ProportionalTaintEngine(G, victim_account, victim_tainted_amount)
    engine.propagate()
    return engine.get_all_taints()
