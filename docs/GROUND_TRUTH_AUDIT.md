# GROUND TRUTH DATASET AUDIT & RECONCILIATION

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Dataset**: VoidHacks8 Mule Account 2M Transaction Dataset  
**Status**: AUDITED & RECONCILED  

---

## 1. Raw Dataset Profile

| Metric | Measured Value |
|---|---|
| **File Path** | `C:\Users\anany\Downloads\VoidHacks8_MuleAccount_2M_Transactions.csv` |
| **File Size** | 286,788,986 bytes (273.50 MB) |
| **Raw Row Count** | 2,000,000 rows |
| **Unique Transaction IDs** | 1,997,748 |
| **Duplicate / Invalid Occurrences** | 2,252 duplicate transactions (4,906 flagged occurrences) |
| **Unique Accounts (Total)** | 24,873 accounts |
| **Unique Sender Accounts** | 24,488 accounts |
| **Unique Receiver Accounts** | 24,573 accounts |
| **Date Range** | `2026-09-15 00:00:00` to `2026-09-29 23:59:58` |

### Payment Modes Distribution
| Payment Mode | Transaction Count | Percentage |
|---|---|---|
| **UPI** | 1,299,844 | 64.99% |
| **IMPS** | 441,199 | 22.06% |
| **NEFT** | 199,134 | 9.96% |
| **RTGS** | 59,823 | 2.99% |
| **Total** | 2,000,000 | 100.00% |

### Columns Present in Source CSV
1. `Transaction_ID` (VARCHAR)
2. `Sender_Account` (VARCHAR)
3. `Receiver_Account` (VARCHAR)
4. `Sender_IFSC` (VARCHAR)
5. `Receiver_IFSC` (VARCHAR)
6. `Amount` (DOUBLE)
7. `Timestamp` (TIMESTAMP)
8. `Payment_Mode` (VARCHAR)
9. `Narration` (VARCHAR)
10. `IP_Address` (VARCHAR)
11. `Device_Type` (VARCHAR)

---

## 2. Ingestion & Database Reconciliation

```
RAW CSV: 2,000,000 rows
    ↓
DATA VALIDATION (duplicate transaction ID detection, negative amounts, timestamp format)
    ├── CLEAN PARQUET: 1,997,748 rows (`data/processed/transactions.parquet`, 98.21 MB)
    └── FLAGGED PARQUET: 4,906 rows (`data/processed/transactions_flagged.parquet`, 0.29 MB)
    ↓
DUCKDB PERSISTENCE (`data/abhedya.duckdb`)
    └── Clean Loaded Table: 1,997,748 rows
```

### Reconciliation Root Cause Analysis (Resolved)
- Previously, DuckDB reported **1,997,763 rows** while clean Parquet had **1,997,748 rows**.
- **Root Cause**: An initial development bootstrap inserted 15 synthetic development transactions (`TX001`-`TX015`) into the database. When the clean Parquet was subsequently loaded using `INSERT OR IGNORE`, the table contained $1,997,748 + 15 = 1,997,763$ rows.
- **Resolution**: DuckDB was re-initialized strictly from the clean Parquet (`data/processed/transactions.parquet`), ensuring a 100% exact match of **1,997,748 clean rows**. Test fixtures were modified to restore the clean Parquet upon test session teardown.

---

## 3. Ground Truth Data Flow

```
LOCAL 2M CSV / PARQUET
        ↓
DUCKDB INDEXED PERSISTENCE (`idx_sender`, `idx_receiver`, `idx_timestamp`)
        ↓
BOUNDED BFS SUBGRAPH TRAVERSAL (Max 4 hops / 500 nodes)
        ↓
CHRONOLOGICAL FLOW ANALYSIS (`timestamp ASC`)
        ↓
PROPORTIONAL TAINT PROPAGATION
        ↓
EXPLAINABLE RISK SCORING (0-100)
        ↓
MAX-FLOW / MIN-CUT FREEZE PRIORITY
        ↓
TRACEABLE EVIDENCE ENGINE
        ↓
OLLAMA / TEMPLATE AI NARRATIVE (Validated against ground-truth facts)
        ↓
PDF REPORT & JUDGE MODE API
```

---

## 4. Ground Truth Guarantees

1. **No Synthetic Fallback**: Real investigations (`GET /api/investigate/{account_id}`) and Judge Mode (`GET /api/judge/demo`) strictly query the 1,997,748 DuckDB database.
2. **Explicit Feature Availability**: Features not present in the dataset (such as physical ATM cash-out transactions or cryptocurrency wallets) are explicitly reported as `UNAVAILABLE_FROM_DATASET` rather than being simulated or fabricated.
3. **Traceability**: Every graph edge, timeline item, and evidence record retains its source `transaction_id`, timestamp, amount, and payment mode.
