"""
graph_builder.py — Subgraph construction and L1/L2/L3 layer labeling

KEY DESIGN PRINCIPLE:
- We do NOT load the full 2M transaction dataset into NetworkX.
- We first identify relevant accounts via BFS through DuckDB queries.
- Only the relevant subgraph is loaded into NetworkX for analytics.

Layer labels:
  VICTIM = the starting account
  L1     = direct recipients from victim
  L2     = recipients from L1
  L3     = recipients from L2 (or terminal cash-out nodes)
  UNKNOWN = beyond 4 hops (not traced in detail)

STATUS: IMPLEMENTED
"""
import logging
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque

import networkx as nx

from backend.config import MAX_HOPS, SUBGRAPH_LIMIT
from backend.db import queries as db
from backend.models.schemas import GraphNode, GraphEdge, GraphData

logger = logging.getLogger(__name__)


def _ifsc_to_bank(ifsc: Optional[str]) -> str:
    """Extract bank code from IFSC (first 4 chars)."""
    if not ifsc or len(ifsc) < 4:
        return "UNKNOWN"
    return ifsc[:4].upper()


def _layer_label(hop: int) -> str:
    labels = {0: "VICTIM", 1: "L1", 2: "L2", 3: "L3"}
    return labels.get(hop, "L3+")


def discover_subgraph_accounts(
    victim_account: str,
    max_hops: int = MAX_HOPS
) -> Dict[str, int]:
    """
    BFS through DuckDB to discover all accounts reachable from victim
    within max_hops directed hops (following money flow: sender → receiver).

    Returns: dict of {account_id: hop_distance}
    This runs against DuckDB — NOT against an in-memory graph.
    """
    visited: Dict[str, int] = {victim_account: 0}  # account → hop
    frontier: deque = deque([(victim_account, 0)])

    while frontier:
        current_account, hop = frontier.popleft()

        if hop >= max_hops:
            continue

        if len(visited) >= SUBGRAPH_LIMIT:
            logger.warning(
                f"Subgraph limit ({SUBGRAPH_LIMIT} nodes) reached. "
                "Truncating traversal. Consider a smaller hop limit."
            )
            break

        # Follow money outward (victim sends → L1 receives → L2 ...)
        outgoing = db.get_outgoing_transactions(current_account)
        for tx in outgoing:
            receiver = tx["receiver_account"]
            if receiver not in visited:
                visited[receiver] = hop + 1
                frontier.append((receiver, hop + 1))

    return visited


def build_graph(victim_account: str, max_hops: int = MAX_HOPS) -> Tuple[nx.DiGraph, Dict[str, int]]:
    """
    Build a directed NetworkX graph for the relevant subgraph.

    Returns:
        G: NetworkX DiGraph (nodes=accounts, edges=transactions)
        layers: dict of {account_id: hop_distance}
    """
    # Step 1: Discover relevant accounts via BFS through DuckDB
    layers = discover_subgraph_accounts(victim_account, max_hops)
    account_ids = list(layers.keys())

    logger.info(
        f"Subgraph for {victim_account}: {len(account_ids)} accounts discovered "
        f"({max_hops}-hop BFS)."
    )

    # Step 2: Fetch only relevant transactions from DuckDB
    transactions = db.get_subgraph_transactions(account_ids)

    # Step 3: Build NetworkX graph
    G = nx.DiGraph()

    # Add nodes
    for account_id, hop in layers.items():
        G.add_node(account_id, layer=_layer_label(hop), hop=hop)

    # Add edges (each transaction is a directed edge sender → receiver)
    for tx in transactions:
        sender = tx["sender_account"]
        receiver = tx["receiver_account"]

        # Only add edge if both nodes are in our subgraph
        if sender not in layers or receiver not in layers:
            continue

        G.add_edge(
            sender,
            receiver,
            transaction_id=tx["transaction_id"],
            amount=float(tx["amount"]),
            timestamp=tx["timestamp"],
            payment_mode=tx.get("payment_mode"),
            sender_ifsc=tx.get("sender_ifsc"),
            receiver_ifsc=tx.get("receiver_ifsc"),
            # SECURITY: narration stored but marked untrusted
            narration_raw=tx.get("narration"),
            ip_address=tx.get("ip_address"),
            device_type=tx.get("device_type"),
        )

    logger.info(
        f"NetworkX graph built: {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges."
    )

    return G, layers


def graph_to_schema(
    G: nx.DiGraph,
    layers: Dict[str, int],
    risk_scores: Optional[Dict[str, float]] = None,
    taint_amounts: Optional[Dict[str, float]] = None,
    taint_results: Optional[Dict[str, Any]] = None,
) -> GraphData:
    """
    Convert NetworkX graph to Pydantic schema for API response.
    Aggregates multiple transactions between the same pair of nodes.
    """
    # Build nodes — strictly deduplicated by account_id
    nodes: List[GraphNode] = []
    seen_nodes: Set[str] = set()
    for node_id in G.nodes():
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        hop = layers.get(node_id, 99)
        layer = _layer_label(hop)

        # Bank: try to infer from IFSC of any edge
        bank = "UNKNOWN"
        for _, tgt, data in G.out_edges(node_id, data=True):
            ifsc = data.get("sender_ifsc")
            if ifsc:
                bank = _ifsc_to_bank(ifsc)
                break
        if bank == "UNKNOWN":
            for src, _, data in G.in_edges(node_id, data=True):
                ifsc = data.get("receiver_ifsc")
                if ifsc:
                    bank = _ifsc_to_bank(ifsc)
                    break

        t_amt = None
        if taint_amounts and node_id in taint_amounts:
            t_amt = taint_amounts[node_id]
        elif taint_results and node_id in taint_results:
            tr = taint_results[node_id]
            t_amt = getattr(tr, "tainted_amount", tr.get("tainted_amount", None) if isinstance(tr, dict) else None)

        nodes.append(GraphNode(
            id=node_id,
            label=node_id,
            layer=layer,
            risk_score=risk_scores.get(node_id) if risk_scores else None,
            tainted_amount=t_amt,
            bank=bank,
        ))

    # Build edges (one per transaction for full detail and traceability)
    edges: List[GraphEdge] = []
    for src, tgt, data in G.edges(data=True):
        tx_amt = float(data.get("amount", 0))
        edge_taint = None
        if taint_results and src in taint_results:
            tr = taint_results[src]
            ratio = getattr(tr, "taint_ratio", tr.get("taint_ratio", 0.0) if isinstance(tr, dict) else 0.0)
            edge_taint = round(tx_amt * float(ratio), 2)

        edges.append(GraphEdge(
            source=src,
            target=tgt,
            amount=tx_amt,
            tainted_amount=edge_taint,
            timestamp=str(data.get("timestamp", "")),
            transaction_id=str(data.get("transaction_id", "")),
            payment_mode=data.get("payment_mode"),
            sender_ifsc=data.get("sender_ifsc"),
            receiver_ifsc=data.get("receiver_ifsc"),
        ))

    return GraphData(nodes=nodes, edges=edges)


def get_terminal_nodes(G: nx.DiGraph) -> List[str]:
    """
    Terminal nodes = accounts with no outgoing edges in our subgraph.
    These represent cash-out / exit points.
    """
    return [n for n in G.nodes() if G.out_degree(n) == 0]


def get_cycles(G: nx.DiGraph, max_cycles: int = 50) -> List[List[str]]:
    """
    Detect simple cycles in the graph (bounded by max_cycles to prevent exponential blowup on dense graphs).
    Cycles suggest obfuscation / layering tactics.
    """
    try:
        import itertools
        return list(itertools.islice(nx.simple_cycles(G), max_cycles))
    except Exception as e:
        logger.warning(f"Cycle detection error: {e}")
        return []

