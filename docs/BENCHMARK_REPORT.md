# PERFORMANCE BENCHMARK REPORT — OPERATION ABHEDYA-CHAKRA

**Date:** 2026-10-02 07:05:00
**Dataset:** Real Local DuckDB Ingestion (~2,000,000 transactions)
**Scope:** End-to-end validation of Ingestion, DuckDB Lookups, and Investigation API

---

## 1. INGESTION & DATASET BENCHMARK (Tier 1)

| Metric | Measured Value | Notes |
|---|---|---|
| Total Transactions Ingested | 2,000,000 rows | Real hackathon dataset |
| Clean Rows Loaded in DuckDB | 1,997,748 rows | Deduplicated & normalized |
| Distinct Sender Accounts | 24,488 | Indexed column |
| Distinct Receiver Accounts | 24,573 | Indexed column |
| Ingestion Pipeline Time | 2.073 s | CSV -> Validate -> Parquet |
| Ingestion Throughput | 964,785 rows/sec | Sub-3s for 2M rows |
| Parquet Storage Size | 98.21 MB | Snappy compressed columnar |
| DuckDB Storage Size | 677.76 MB | Indexed local analytical DB |
| Full-Table Scan Latency | 76.38 ms | DuckDB engine query |

---

## 2. DUCKDB QUERY PERFORMANCE BENCHMARK (Tier 2)

| Query Operation | Average (ms) | Median / p50 (ms) | p95 (ms) |
|---|---|---|---|
| Account Summary Aggregation | 39.186 ms | 37.976 ms | 55.371 ms |
| Account Transaction Fetch | 52.039 ms | 51.301 ms | 60.468 ms |

---

## 3. INVESTIGATION API BENCHMARK (Tier 3: GET /api/investigate/{account_id})

Pipeline executed per request:
1. Parameterized DuckDB account query
2. Multi-hop BFS subgraph discovery (up to 4 hops)
3. NetworkX directed graph construction
4. Mule detection rules (Fan-in, Fan-out, Velocity, Multi-hop, Cycles, Cross-bank, Devices)
5. Explainable Mule Risk Index scoring (0–100)
6. Proportional Tainted-balance propagation
7. Freeze Priority Engine (Max-flow / Min-cut optimization)
8. Traceable evidence package assembly
9. Chronological transaction timeline ordering

### Overall Latency Summary

| Metric | Measured Latency | Target (Project Brief) | Status |
|---|---|---|---|
| **Min Latency** | **787.74 ms** | < 2,000 ms | PASS |
| **Median / p50 Latency** | **944.05 ms** | < 2,000 ms | PASS |
| **Average Latency** | **934.44 ms** | < 2,000 ms | PASS |
| **p95 Latency** | **1137.11 ms** | < 2,000 ms | PASS |
| **Max Latency** | **1218.57 ms** | < 2,000 ms | PASS |
| **Successful Requests** | **30 / 30** | 100% | PASS |
| **Failures** | **0** | 0 | PASS |

### Per-Account Breakdown (Sample Tested)

| # | Account ID | Avg Latency (ms) | Subgraph Nodes | Subgraph Edges | Freeze Candidates |
|---|---|---|---|---|---|
| 01 | `SBIN10012624` | 795.16 ms | 544 | 1600 | 61 |
| 02 | `ICIC10006430` | 869.9 ms | 561 | 1733 | 73 |
| 03 | `IPOS10016649` | 829.13 ms | 568 | 1690 | 76 |
| 04 | `AXIS10013687` | 869.75 ms | 548 | 1592 | 55 |
| 05 | `SBIN10023615` | 815.38 ms | 522 | 1485 | 63 |
| 06 | `ICIC10013958` | 916.21 ms | 562 | 1662 | 89 |
| 07 | `PYTM10009109` | 899.24 ms | 542 | 1548 | 71 |
| 08 | `SBIN10015548` | 858.86 ms | 526 | 1460 | 51 |
| 09 | `IPOS10006833` | 948.23 ms | 545 | 1589 | 72 |
| 10 | `AXIS10004774` | 981.32 ms | 548 | 1621 | 78 |
| 11 | `AIRP10016580` | 978.66 ms | 535 | 1590 | 56 |
| 12 | `PUNB10016030` | 974.64 ms | 513 | 1430 | 56 |
| 13 | `KKBK10005746` | 1024.21 ms | 524 | 1541 | 73 |
| 14 | `KKBK10021279` | 1078.01 ms | 547 | 1600 | 44 |
| 15 | `AIRP10003300` | 1177.84 ms | 555 | 1674 | 74 |

---
**Conclusion:** The investigation engine comfortably beats the sub-2-second target across large 4-hop subgraphs containing hundreds of nodes and thousands of transactions.