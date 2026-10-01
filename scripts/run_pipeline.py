"""
run_pipeline.py — CLI entry point for data ingestion
======================================================
Aashna — Data Engineering & Performance Owner

Run this ONCE to import the dataset and prepare the data layer.
After this completes, Gunjan and Ananya can use src/data/query.py.

Usage:
    python scripts/run_pipeline.py

    # Force re-run even if Parquet already exists:
    python scripts/run_pipeline.py --force

Output:
    data/processed/transactions.parquet       (clean records)
    data/processed/transactions_flagged.parquet (validation issues)
    data/processed/validation_report.json     (audit log)
    data/processed/abhedya.duckdb             (persistent DB)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows (avoids UnicodeEncodeError in PowerShell/cmd)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import initialize_database
from src.data.ingestion import CLEAN_PARQUET, PROCESSED_DIR, run_ingestion_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def main():
    parser = argparse.ArgumentParser(
        description="Operation Abhedya-Chakra: Ingest and prepare the data layer"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion even if processed Parquet already exists",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip DuckDB initialization after Parquet write",
    )
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  Operation Abhedya-Chakra — Data Ingestion Pipeline")
    print("  Aashna — Data Engineering & Performance Owner")
    print("═" * 60 + "\n")

    # Check if already processed
    if CLEAN_PARQUET.exists() and not args.force:
        size_mb = CLEAN_PARQUET.stat().st_size / 1024 / 1024
        print(f"✅ Parquet already exists ({size_mb:.1f} MB): {CLEAN_PARQUET}")
        print("   Use --force to re-ingest.\n")

        # Still initialize DuckDB if needed
        if not args.skip_db:
            print("🔌 Initializing DuckDB from existing Parquet...")
            t0 = time.perf_counter()
            con = initialize_database()
            elapsed = time.perf_counter() - t0

            # Quick count check
            count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            print(f"   DuckDB ready: {count:,} rows loaded in {elapsed:.2f}s\n")
        return

    # Stage 1–4: Ingestion pipeline
    print("🚀 Starting ingestion pipeline...\n")
    report = run_ingestion_pipeline()

    # Print summary
    print("\n" + "─" * 60)
    print("  INGESTION SUMMARY")
    print("─" * 60)
    print(f"  Total rows:          {report.get('total_rows', 0):>12,}")
    print(f"  Clean rows:          {report.get('clean_rows', 0):>12,}")
    print(f"  Flagged rows:        {report.get('flagged_rows', 0):>12,}")
    print(f"    ↳ Duplicate IDs:   {report.get('duplicate_ids', 0):>12,}")
    print(f"    ↳ Invalid amounts: {report.get('invalid_amounts', 0):>12,}")
    print(f"    ↳ Missing fields:  {report.get('missing_fields', 0):>12,}")
    print(f"    ↳ Malformed ts:    {report.get('malformed_timestamps', 0):>12,}")
    print(f"    ↳ Suspicious dev:  {report.get('suspicious_devices', 0):>12,}")
    print(f"    ↳ Invalid pm:      {report.get('invalid_payment_modes', 0):>12,}")
    print()
    print(f"  Read CSV:            {report.get('read_csv_seconds', 0):>10.2f}s")
    print(f"  Validate:            {report.get('validate_seconds', 0):>10.2f}s")
    print(f"  Normalize:           {report.get('normalize_seconds', 0):>10.2f}s")
    print(f"  Write Parquet:       {report.get('write_parquet_seconds', 0):>10.2f}s")
    print(f"  TOTAL:               {report.get('total_seconds', 0):>10.2f}s")
    print(f"  Throughput:          {report.get('rows_per_second', 0):>10,.0f} rows/s")
    print("─" * 60)

    # Check Parquet size
    if CLEAN_PARQUET.exists():
        size_mb = CLEAN_PARQUET.stat().st_size / 1024 / 1024
        print(f"\n  Parquet size: {size_mb:.1f} MB → {CLEAN_PARQUET.name}")

    flagged_path = PROCESSED_DIR / "transactions_flagged.parquet"
    if flagged_path.exists():
        size_mb = flagged_path.stat().st_size / 1024 / 1024
        print(f"  Flagged size: {size_mb:.1f} MB → {flagged_path.name}")

    # Stage 5: Initialize DuckDB
    if not args.skip_db:
        print("\n🔌 Initializing DuckDB...")
        t0 = time.perf_counter()
        con = initialize_database()
        elapsed = time.perf_counter() - t0
        count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        print(f"   DuckDB ready: {count:,} rows, {elapsed:.2f}s\n")

    print("\n✅ Data layer ready.")
    print("   Gunjan and Ananya: import from src.data.query\n")


if __name__ == "__main__":
    main()
