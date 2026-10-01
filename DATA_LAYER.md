# Operation Abhedya-Chakra — Data Layer Documentation

**Aashna — Data Engineering & Performance Owner**  
VoidHacks 8.0 | Offline-First Financial Transaction Investigation Platform

---

## Overview

The data layer ingests a 2,000,000-row transaction dataset into a fast, offline, queryable store using **Polars** (ingestion), **Parquet** (storage), and **DuckDB** (query engine). It exposes a clean Python API that Gunjan (graph engine) and Ananya (FastAPI) can call without knowing any internal storage details.

---

## 1. Installation

```bash
pip install -r requirements.txt
```

**Required packages:**
- `polars` — vectorized CSV processing and Parquet I/O  
- `duckdb` — embedded SQL analytics engine  
- `pyarrow` — Parquet format support  
- `pytest` — unit testing  

---

## 2. Importing the Dataset

Run once after cloning the repo:

```bash
python scripts/run_pipeline.py
```

This will:
1. Read `data/raw/VoidHacks8_MuleAccount_2M_Transactions.csv` (273 MB)
2. Validate all 2,000,000 rows
3. Write clean records to `data/processed/transactions.parquet`
4. Write flagged records to `data/processed/transactions_flagged.parquet`
5. Write `data/processed/validation_report.json`
6. Initialize `data/processed/abhedya.duckdb`

To force a re-run:
```bash
python scripts/run_pipeline.py --force
```

> **Note:** `data/raw/` and `data/processed/` are both gitignored. Teammates must run the pipeline locally.

---

## 3. How the Dataset is Stored

```
data/
├── raw/
│   └── VoidHacks8_MuleAccount_2M_Transactions.csv   ← NEVER MODIFIED (273 MB)
└── processed/
    ├── transactions.parquet           ← Clean records (~40–60 MB, snappy)
    ├── transactions_flagged.parquet   ← Flagged records (duplicates, suspicious)
    ├── validation_report.json         ← Audit log with counts and timings
    └── abhedya.duckdb                 ← DuckDB persistent database
```

### What gets flagged (not deleted)

| Flag | Meaning |
|---|---|
| `duplicate_id` | Transaction ID appears more than once; first kept in clean |
| `invalid_amount` | Amount ≤ 0 or null |
| `missing_required_field` | Null in sender/receiver/timestamp/IFSC/IP/payment_mode |
| `malformed_timestamp` | Timestamp does not parse as `YYYY-MM-DD HH:MM:SS` |
| `invalid_payment_mode` | Payment mode outside `{IMPS, UPI, RTGS, NEFT}` |
| `suspicious_device` | `Web_Emulator` or `Linux_Script` — **also kept in clean data** |

---

## 4. How DuckDB is Used

DuckDB operates as a zero-copy view over the Parquet files. It does **not** load 2M rows into RAM at startup — it reads only the columns and rows each query needs (predicate pushdown).

The `data/processed/abhedya.duckdb` file holds persistent view registrations:
```sql
CREATE OR REPLACE VIEW transactions AS
SELECT * FROM read_parquet('data/processed/transactions.parquet')
```

**You never need to write SQL.** Use `src/data/query.py` instead.

---

## 5. How Parquet is Used

- Format: Apache Parquet, Snappy compression
- Columnar layout means DuckDB can read only the columns a query needs
- Example: a query for `sender_account` never reads `narration` from disk
- Estimated size: ~40–60 MB (vs 273 MB CSV = ~5–7x compression)

---

## 6. How to Run Benchmarks

```bash
# Run the ingestion pipeline first
python scripts/run_pipeline.py

# Then run benchmarks
python scripts/benchmark.py
```

The benchmark measures real timings for:
- CSV read (2M rows)
- Validation
- Normalization
- Parquet write
- DuckDB startup
- Account lookup latency
- Incoming/outgoing query latency
- Counterparty query latency
- Time-range query latency
- Peak memory usage

All values are **measured**, never invented.

---

## 7. Gunjan's Guide — Graph Layer Integration

**Import only from `src/data/query`:**

```python
from src.data.query import (
    get_account_transactions,
    get_incoming_transactions,
    get_outgoing_transactions,
    get_counterparties,
    get_transactions_between,
    get_account_summary,
    get_transaction,
)
```

### Starting from a seed account

```python
# Get all transactions involving this account
txns = get_account_transactions("KKBK10000000")

# Build graph edges
for tx in txns:
    graph.add_edge(
        tx.sender_account,
        tx.receiver_account,
        transaction_id=tx.transaction_id,
        amount=tx.amount,
        timestamp=tx.timestamp,
        payment_mode=tx.payment_mode,
    )
```

### Expanding to counterparties (1-hop)

```python
counterparties = get_counterparties("KKBK10000000")
# counterparties["all_counterparties"] → list of all connected accounts

for account in counterparties["all_counterparties"]:
    hop_txns = get_account_transactions(account)
    # Add edges to graph...
```

### Transaction object fields

```python
tx.transaction_id    # str, e.g. "TXN401119292"
tx.sender_account    # str, e.g. "KKBK10000000"
tx.receiver_account  # str, e.g. "ICIC10000335"
tx.sender_ifsc       # str, e.g. "KKBK0001000"
tx.receiver_ifsc     # str, e.g. "ICIC0001335"
tx.amount            # float, e.g. 455541.61
tx.timestamp         # datetime object
tx.payment_mode      # str: "UPI" | "IMPS" | "NEFT" | "RTGS"
tx.narration         # str, free text
tx.ip_address        # str, IPv4
tx.device_type       # str: "ANDROID" | "IOS" | "WINDOWS_BROWSER" | "WEB_EMULATOR" | "LINUX_SCRIPT"
tx.as_dict()         # → JSON-serializable dict
```

> **Important:** `device_type` values are uppercased during normalization (e.g., `Android` → `ANDROID`).

### Account summary

```python
summary = get_account_summary("KKBK10000000")
# Returns AccountSummary with:
summary.incoming_transaction_count
summary.outgoing_transaction_count
summary.total_incoming_amount
summary.total_outgoing_amount
summary.unique_incoming_accounts
summary.unique_outgoing_accounts
summary.first_transaction_timestamp  # datetime
summary.last_transaction_timestamp   # datetime
summary.as_dict()  # JSON-serializable
```

### Pagination (for accounts with thousands of transactions)

```python
from src.data.query import get_account_transactions_paginated

page_1 = get_account_transactions_paginated("KKBK10000000", limit=500, offset=0)
page_2 = get_account_transactions_paginated("KKBK10000000", limit=500, offset=500)
```

---

## 8. Ananya's Guide — FastAPI Integration

**Import from `src/data/query` in your route handlers:**

```python
from src.data.query import (
    get_account_summary,
    get_account_transactions,
    get_dataset_stats,
    get_flagged_transactions,
)

@app.get("/api/account/{account_id}/summary")
def account_summary(account_id: str):
    summary = get_account_summary(account_id)
    return summary.as_dict()  # Already JSON-serializable

@app.get("/api/account/{account_id}/transactions")
def account_transactions(account_id: str, limit: int = 100, offset: int = 0):
    from src.data.query import get_account_transactions_paginated
    txns = get_account_transactions_paginated(account_id, limit=limit, offset=offset)
    return [tx.as_dict() for tx in txns]

@app.get("/api/stats")
def dataset_stats():
    return get_dataset_stats()
```

**DuckDB connection is initialized once** at startup. No need to manage connections:

```python
# In main.py startup event:
from src.data.database import initialize_database

@app.on_event("startup")
def startup():
    initialize_database()
```

---

## 9. Offline Operation

The entire system runs **fully offline**. There are no external API calls, cloud dependencies, or network requirements in the data layer. Everything runs from:
- The local CSV file in `data/raw/`
- The generated Parquet files in `data/processed/`
- The local DuckDB file in `data/processed/`

---

## 10. Running Tests

```bash
# From project root
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ -v --cov=src/data --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_query.py -v
python -m pytest tests/test_validation.py -v
python -m pytest tests/test_ingestion.py -v
```

Tests use **small synthetic datasets only** (50–200 rows). The 273 MB dataset is never loaded during testing.

---

## Dataset Audit Reference

| Field | Value |
|---|---|
| File | `VoidHacks8_MuleAccount_2M_Transactions.csv` |
| Size | 273.50 MB |
| Rows | 2,000,000 |
| Columns | 11 (exact schema match) |
| Missing values | 0 |
| Duplicate IDs | 2,250 (0.11%) |
| Suspicious devices | 2,654 (Web_Emulator: 1,327 + Linux_Script: 1,327) |
| Timestamp range | 2026-09-15 → 2026-09-29 (15 days) |
| Unique senders | 24,488 |
| Unique receivers | 24,573 |
| Payment modes | UPI 65%, IMPS 22%, NEFT 10%, RTGS 3% |
