"""
src/graph/detector.py
=====================
Module B: Mule Ring Detection & Graph Analytics Engine
Optimized for <= 2.0s 4-Hop Benchmark Latency
"""

from collections import deque
from typing import Dict, List, Any
import duckdb
from src.data.database import get_connection

class FraudGraphDetector:
    def __init__(self):
        pass

    def trace_victim_flow(self, victim_account: str, max_hops: int = 4) -> Dict[str, Any]:
        """
        Batch BFS downstream traversal to consistently hit < 0.5s latency.
        """
        victim_account = str(victim_account).strip()
        visited_hops = {victim_account: 0}
        current_layer = [victim_account]
        
        edges = []
        seen_tx_ids = set()
        con = get_connection()

        for hop in range(1, max_hops + 1):
            if not current_layer:
                break

            # Batch query all outgoing transactions for the entire layer
            placeholders = ", ".join(["?"] * len(current_layer))
            query = f"""
                SELECT 
                    transaction_id,
                    sender_account,
                    receiver_account,
                    amount,
                    timestamp,
                    payment_mode,
                    ip_address,
                    narration,
                    device_type
                FROM transactions
                WHERE sender_account IN ({placeholders})
            """
            rows = con.execute(query, current_layer).fetchall()

            next_layer = []
            for r in rows:
                tx_id, s, rec, amt, ts, mode, ip, narr, dev = r
                s, rec = str(s), str(rec)

                if tx_id not in seen_tx_ids:
                    seen_tx_ids.add(tx_id)
                    edges.append({
                        "transaction_id": tx_id,
                        "source": s,
                        "target": rec,
                        "amount": float(amt),
                        "timestamp": str(ts),
                        "payment_mode": str(mode),
                        "ip_address": str(ip),
                        "narration": str(narr),
                        "device_type": str(dev),
                        "hop": hop
                    })

                if rec not in visited_hops:
                    visited_hops[rec] = hop
                    next_layer.append(rec)

            current_layer = next_layer

        # Batch analyze discovered nodes
        nodes = self._batch_evaluate_nodes(list(visited_hops.keys()), visited_hops, con)

        return {
            "victim_account": victim_account,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes,
            "edges": edges
        }

    def _batch_evaluate_nodes(self, accounts: List[str], hops: Dict[str, int], con) -> List[Dict[str, Any]]:
        if not accounts:
            return []

        placeholders = ", ".join(["?"] * len(accounts))

        # 1. Incoming aggregations (Fan-In)
        in_query = f"""
            SELECT 
                receiver_account,
                COUNT(DISTINCT sender_account) as in_deg,
                SUM(amount) as total_in
            FROM transactions
            WHERE receiver_account IN ({placeholders})
            GROUP BY receiver_account
        """
        in_metrics = {r[0]: (r[1], float(r[2])) for r in con.execute(in_query, accounts).fetchall()}

        # 2. Outgoing aggregations (Fan-Out & Terminal checks)
        out_query = f"""
            SELECT 
                sender_account,
                COUNT(DISTINCT receiver_account) as out_deg,
                SUM(amount) as total_out,
                BOOL_OR(ip_address LIKE '185.%' OR ip_address LIKE '194.%') as foreign_ip,
                BOOL_OR(device_type IN ('Web_Emulator', 'Linux_Script')) as script_dev,
                BOOL_OR(
                    LOWER(narration) LIKE '%crypto%' OR 
                    LOWER(narration) LIKE '%p2p%' OR 
                    LOWER(narration) LIKE '%binance%' OR 
                    LOWER(narration) LIKE '%usdt%' OR 
                    LOWER(narration) LIKE '%wallet%'
                ) as crypto_narr
            FROM transactions
            WHERE sender_account IN ({placeholders})
            GROUP BY sender_account
        """
        out_metrics = {
            r[0]: {
                "out_deg": r[1],
                "total_out": float(r[2]),
                "foreign_ip": r[3],
                "script_dev": r[4],
                "crypto_narr": r[5]
            } for r in con.execute(out_query, accounts).fetchall()
        }

        evaluated = []
        for acc in accounts:
            in_deg, total_in = in_metrics.get(acc, (0, 0.0))
            out_info = out_metrics.get(acc, {
                "out_deg": 0, "total_out": 0.0, "foreign_ip": False, "script_dev": False, "crypto_narr": False
            })

            out_deg = out_info["out_deg"]
            total_out = out_info["total_out"]
            score = 0
            layer = "Normal"
            flags = []

            # L1: Fan-In
            if in_deg >= 3:
                score += 35
                layer = "L1_Collector"
                flags.append(f"Fan-In Detected ({in_deg} senders)")

            # L2: Fan-Out
            if 3 <= out_deg <= 7:
                score += 35
                layer = "L2_Distributor"
                flags.append(f"Fan-Out Detected ({out_deg} receivers)")

            # Velocity Pass-Through
            if total_in > 0 and (total_out / total_in) >= 0.90:
                score += 25
                flags.append(f"Velocity Pass-Through ({(total_out/total_in)*100:.1f}%)")

            # L3: Terminal Indicators
            if out_info["foreign_ip"]:
                score += 40
                layer = "L3_Terminal"
                flags.append("Foreign IP Proxy Detected")
            if out_info["script_dev"]:
                score += 35
                layer = "L3_Terminal"
                flags.append("Automated Script/Emulator Device")
            if out_info["crypto_narr"]:
                score += 30
                layer = "L3_Terminal"
                flags.append("Crypto/P2P Narration Flag")

            final_score = min(score, 100)
            hop = hops.get(acc, 0)

            if hop == 1 and layer == "Normal" and final_score >= 30:
                layer = "L1_Collector"
            elif hop in [2, 3] and layer == "Normal" and final_score >= 30:
                layer = "L2_Distributor"

            evaluated.append({
                "account": acc,
                "hop": hop,
                "mule_risk_score": final_score,
                "layer": layer,
                "in_degree": in_deg,
                "out_degree": out_deg,
                "total_in": total_in,
                "total_out": total_out,
                "flags": flags,
                "recommended_freeze": final_score >= 60
            })

        return evaluated