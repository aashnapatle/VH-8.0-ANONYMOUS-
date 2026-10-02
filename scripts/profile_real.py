import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
import duckdb
from backend.db import loader, queries as db
from backend.services import graph_builder, detection, risk_engine, taint_engine, freeze_engine, evidence_builder, timeline

def profile_investigation(account_id: str, max_hops: int = 4):
    print(f"\n--- Profiling Investigation for {account_id} (max_hops={max_hops}) ---")
    
    t0 = time.perf_counter()
    exists = db.account_exists(account_id)
    t1 = time.perf_counter()
    print(f"1. Account exists check: {(t1 - t0)*1000:.2f} ms")
    if not exists:
        print("Account does not exist!")
        return

    t0 = time.perf_counter()
    G, layers = graph_builder.build_graph(account_id, max_hops)
    t1 = time.perf_counter()
    print(f"2. Build graph & BFS discovery ({len(layers)} accounts, {G.number_of_nodes()} nodes, {G.number_of_edges()} edges): {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    all_account_ids = list(layers.keys())
    all_txns = db.get_subgraph_transactions(all_account_ids)
    t1 = time.perf_counter()
    print(f"3. Fetch subgraph transactions ({len(all_txns)} txns): {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    cycles = graph_builder.get_cycles(G) if detection.CYCLE_DETECTION_ENABLED else []
    dev_map, ip_map = detection.build_overlap_indexes(all_txns)
    all_account_signals = {}
    for acc_id in all_account_ids:
        acc_txns = [
            t for t in all_txns
            if t["sender_account"] == acc_id or t["receiver_account"] == acc_id
        ]
        signals = detection.run_all_detection(
            G, acc_id, acc_txns, layers, all_txns, cycles=cycles,
            device_to_accounts=dev_map, ip_to_accounts=ip_map,
        )
        all_account_signals[acc_id] = signals
    t1 = time.perf_counter()
    print(f"4. Run detection signals for {len(all_account_ids)} accounts: {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    risk_scores = risk_engine.compute_risk_scores_for_subgraph(all_account_ids, all_account_signals)
    t1 = time.perf_counter()
    print(f"5. Compute risk scores: {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    taint_results = taint_engine.run_taint_analysis(G, account_id)
    t1 = time.perf_counter()
    print(f"6. Taint analysis: {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    freeze_plan = freeze_engine.compute_freeze_priority(G, account_id, taint_results, risk_scores, layers)
    t1 = time.perf_counter()
    print(f"7. Freeze priority: {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    evidence = evidence_builder.build_full_evidence_package(all_txns, taint_results, risk_scores, freeze_plan, account_id, layers)
    t1 = time.perf_counter()
    print(f"8. Build evidence ({len(evidence)} items): {(t1 - t0)*1000:.2f} ms")

    t0 = time.perf_counter()
    tl_events = timeline.build_timeline(all_txns, layers, account_id)
    t1 = time.perf_counter()
    print(f"9. Build timeline ({len(tl_events)} events): {(t1 - t0)*1000:.2f} ms")

if __name__ == "__main__":
    profile_investigation("KKBK10013350", max_hops=3)
    profile_investigation("SBIN10012624", max_hops=2)
