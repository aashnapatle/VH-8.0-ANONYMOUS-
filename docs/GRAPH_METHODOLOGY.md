# GRAPH & HOP TRAVERSAL METHODOLOGY

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Graph Implementation**: DuckDB Indexed BFS + NetworkX DiGraph Subgraph  

---

## 1. High-Performance Subgraph Extraction

Loading all 2,000,000 transactions into an in-memory graph for every query is prohibitive. Instead, Abhedya-Chakra uses a **two-phase bounded query pipeline**:

```
Phase 1: DuckDB Breadth-First Search (BFS)
   Victim Account (Hop 0)
        ↓  (Query DuckDB: SELECT receiver_account WHERE sender_account = ?)
   L1 Accounts (Hop 1)
        ↓
   L2 Accounts (Hop 2)
        ↓
   L3 Accounts (Hop 3)
        ↓
   L4 Accounts (Hop 4)
   [Safety Cap: 500 nodes max to prevent unbounded fanout explosion]

Phase 2: Subgraph Edge Fetch
   SELECT * FROM transactions 
   WHERE sender_account IN (Discovered_Accounts) 
     AND receiver_account IN (Discovered_Accounts)
   ORDER BY timestamp ASC

Phase 3: NetworkX DiGraph Subgraph Construction
   Nodes = Deduplicated Accounts (annotated with Layer, Bank, IFSC)
   Edges = Actual Transactions (annotated with TxID, Amount, Mode, Timestamp)
```

---

## 2. Layer & Hop Definitions

| Hop Distance | Layer Label | Definition |
|---|---|---|
| **Hop 0** | `VICTIM` | The originating account under investigation |
| **Hop 1** | `L1` | Direct first-level recipients of victim funds |
| **Hop 2** | `L2` | Intermediate mule accounts receiving funds from L1 |
| **Hop 3** | `L3` | Distribution / layer 3 accounts |
| **Hop 4+** | `L3+` | Extended terminal or cash-out exit accounts |

---

## 3. Node Deduplication & Multi-Edge Integrity

1. **Strict Node Uniqueness**: Each account appears exactly once in the `nodes` array, even if it participates in hundreds of transactions.
2. **Multi-Edge Preservation**: If Account A sends money to Account B 5 times across different timestamps or payment modes, each transfer remains distinct with its unique `transaction_id` in the API output and transaction chain.
3. **Traceability**: Every edge is directly verifiable against the underlying database row:
   $$\text{GraphEdge} \longleftrightarrow \text{DuckDB Row} \longleftrightarrow \text{Clean Parquet Row} \longleftrightarrow \text{Source CSV Row}$$
