"""
benchmark.py — Performance benchmarking script
===============================================
Aashna — Data Engineering & Performance Owner

Measures REAL performance numbers for the data layer.
All values are measured, never invented.

Requirements:
    - Run `python scripts/run_pipeline.py` first to generate Parquet + DuckDB
    - Then run: python scripts/benchmark.py

Output: formatted performance table with real measurements.
"""

import sys
import time
import tracemalloc
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import initialize_database, reset_connection
from src.data.ingestion import CLEAN_PARQUET, RAW_CSV
from src.data.query import (
    get_account_summary,
    get_accounts_by_sender,
    get_counterparties,
    get_dataset_stats,
    get_incoming_transactions,
    get_outgoing_transactions,
    get_transaction_count,
    get_transactions_between,
)


def _time_it(fn, *args, runs: int = 3) -> tuple[float, any]:
    """Run fn(*args) `runs` times and return (best_ms, last_result)."""
    best = float("inf")
    result = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn(*args)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms < best:
            best = elapsed_ms
    return round(best, 2), result


def _divider(char="─", width=68):
    print(char * width)


def _row(label: str, value: str, width: int = 68):
    print(f"  {label:<40} {value:>24}")


def main():
    print()
    _divider("═")
    print("  OPERATION ABHEDYA-CHAKRA — PERFORMANCE BENCHMARK")
    print("  Aashna — Data Engineering & Performance Owner")
    _divider("═")
    print()

    # ── Pre-checks ─────────────────────────────────────────────────────────────
    if not CLEAN_PARQUET.exists():
        print("❌ Parquet not found. Run: python scripts/run_pipeline.py first.")
        sys.exit(1)

    parquet_size_mb = CLEAN_PARQUET.stat().st_size / 1024 / 1024
    raw_size_mb = RAW_CSV.stat().st_size / 1024 / 1024 if RAW_CSV.exists() else 0

    # ── 1. Ingestion benchmark (re-read CSV, time the full pipeline) ───────────
    _divider()
    print("  1. INGESTION PIPELINE BENCHMARK")
    _divider()
    print("  Timing: CSV read + validate + normalize + Parquet write")
    print("  (This re-runs the pipeline on the real 2M dataset)\n")

    from src.data.ingestion import read_raw_csv, validate, normalize, write_parquet
    import tempfile, os

    tracemalloc.start()
    t_read = time.perf_counter()
    raw_df = read_raw_csv()
    read_s = time.perf_counter() - t_read

    t_val = time.perf_counter()
    clean_df, flagged_df, val_summary = validate(raw_df)
    val_s = time.perf_counter() - t_val

    t_norm = time.perf_counter()
    clean_df = normalize(clean_df)
    norm_s = time.perf_counter() - t_norm

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        t_write = time.perf_counter()
        # Temporarily override paths
        from src.data import ingestion as _ing
        orig_clean = _ing.CLEAN_PARQUET
        orig_flagged = _ing.FLAGGED_PARQUET
        _ing.CLEAN_PARQUET = tmp_path / "transactions.parquet"
        _ing.FLAGGED_PARQUET = tmp_path / "transactions_flagged.parquet"
        write_parquet(clean_df, flagged_df)
        write_s = time.perf_counter() - t_write
        _ing.CLEAN_PARQUET = orig_clean
        _ing.FLAGGED_PARQUET = orig_flagged

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mem_gb = peak_mem / 1024 / 1024 / 1024

    total_rows = val_summary["total_rows"]
    total_s = read_s + val_s + norm_s + write_s

    _row("Dataset rows", f"{total_rows:,}")
    _row("Raw CSV size", f"{raw_size_mb:.1f} MB")
    _row("Parquet size (clean)", f"{parquet_size_mb:.1f} MB")
    _row("Compression ratio", f"{raw_size_mb / parquet_size_mb:.1f}x")
    print()
    _row("CSV read time", f"{read_s:.2f}s")
    _row("Validation time", f"{val_s:.2f}s")
    _row("Normalization time", f"{norm_s:.2f}s")
    _row("Parquet write time", f"{write_s:.2f}s")
    _row("TOTAL ingestion time", f"{total_s:.2f}s")
    _row("Throughput", f"{total_rows / total_s:,.0f} rows/s")
    _row("Peak memory (ingestion)", f"{peak_mem_gb:.2f} GB")
    print()

    # ── 2. DuckDB startup ──────────────────────────────────────────────────────
    _divider()
    print("  2. DUCKDB STARTUP & QUERY BENCHMARKS")
    _divider()

    reset_connection()  # Force fresh connection
    t0 = time.perf_counter()
    con = initialize_database()
    db_start_s = time.perf_counter() - t0
    _row("DuckDB init (Parquet registration)", f"{db_start_s*1000:.1f} ms")

    # Get total row count
    count_ms, count_val = _time_it(get_transaction_count)
    _row("Total row count query", f"{count_ms:.1f} ms → {count_val:,} rows")
    print()

    # ── 3. Account lookup benchmarks ──────────────────────────────────────────
    # Pick a known account from the dataset
    result = con.execute(
        "SELECT sender_account, COUNT(*) AS c FROM transactions GROUP BY sender_account ORDER BY c DESC LIMIT 3"
    ).fetchall()
    top_accounts = [row[0] for row in result]
    bench_account = top_accounts[0] if top_accounts else "KKBK10000000"
    bench_count = result[0][1] if result else 0

    print(f"  Benchmark account: {bench_account} ({bench_count:,} outgoing txns)\n")

    incoming_ms, incoming_rows = _time_it(get_incoming_transactions, bench_account)
    _row(f"get_incoming_transactions", f"{incoming_ms:.1f} ms → {len(incoming_rows):,} rows")

    outgoing_ms, outgoing_rows = _time_it(get_outgoing_transactions, bench_account)
    _row(f"get_outgoing_transactions", f"{outgoing_ms:.1f} ms → {len(outgoing_rows):,} rows")

    cp_ms, counterparties = _time_it(get_counterparties, bench_account)
    _row(f"get_counterparties", f"{cp_ms:.1f} ms → {len(counterparties['all_counterparties']):,} unique")

    summary_ms, summary = _time_it(get_account_summary, bench_account)
    _row(f"get_account_summary", f"{summary_ms:.1f} ms")
    print()

    # ── 4. Time range query ────────────────────────────────────────────────────
    tr_ms, tr_rows = _time_it(
        get_transactions_between,
        "2026-09-22 00:00:00",
        "2026-09-22 23:59:59",
    )
    _row("get_transactions_between (1 day)", f"{tr_ms:.1f} ms → {len(tr_rows):,} rows")

    # Full dataset stats
    stats_ms, stats = _time_it(get_dataset_stats)
    _row("get_dataset_stats (full scan)", f"{stats_ms:.1f} ms")
    print()

    # ── 5. Cold account (few transactions) ────────────────────────────────────
    result2 = con.execute(
        "SELECT sender_account, COUNT(*) AS c FROM transactions GROUP BY sender_account ORDER BY c ASC LIMIT 1"
    ).fetchone()
    cold_account = result2[0] if result2 else "UNKNOWN"
    cold_ms, cold_rows = _time_it(get_incoming_transactions, cold_account)
    _row(f"Cold account lookup (few txns)", f"{cold_ms:.1f} ms → {len(cold_rows):,} rows")

    # Unknown account
    unknown_ms, unknown_rows = _time_it(get_incoming_transactions, "DOES_NOT_EXIST_99999")
    _row("Unknown account lookup", f"{unknown_ms:.1f} ms → {len(unknown_rows):,} rows")
    print()

    # ── Summary ────────────────────────────────────────────────────────────────
    _divider("═")
    print("  PERFORMANCE SUMMARY")
    _divider("═")
    _row("Ingestion (2M rows)", f"{total_s:.1f}s")
    _row("Throughput", f"{total_rows / total_s:,.0f} rows/s")
    _row("Peak ingestion memory", f"{peak_mem_gb:.2f} GB")
    _row("DuckDB startup", f"{db_start_s*1000:.0f} ms")
    _row("Account lookup p50 (best)", f"{min(incoming_ms, outgoing_ms):.0f} ms")
    _row("Time-range query (1 day)", f"{tr_ms:.0f} ms")
    _row("Dataset stats (full scan)", f"{stats_ms:.0f} ms")
    _divider("═")
    print()
    print("  ✅ Benchmark complete — all values measured, none invented.")
    print()


if __name__ == "__main__":
    main()
