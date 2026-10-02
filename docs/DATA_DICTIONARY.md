# DATA DICTIONARY

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Dataset**: VoidHacks8 Mule Account 2M Transaction Dataset  

---

## 1. Transaction Fields (Source Dataset & Database)

| Column Name | Type | Description | Analytical Usage |
|---|---|---|---|
| `transaction_id` | `VARCHAR` | Unique transaction reference string | Canonical evidence reference for all findings |
| `sender_account` | `VARCHAR` | Alphanumeric account ID of sender | Source node for directed graph edge |
| `receiver_account` | `VARCHAR` | Alphanumeric account ID of recipient | Target node for directed graph edge |
| `sender_ifsc` | `VARCHAR` | 11-character Indian Financial System Code of sender bank | Used for bank extraction (first 4 characters) & cross-bank analysis |
| `receiver_ifsc` | `VARCHAR` | 11-character IFSC of recipient bank | Used for bank extraction & cross-bank analysis |
| `amount` | `DOUBLE` | Transaction value in INR (₹) | Money-flow volume, capacity constraint, and taint calculation |
| `timestamp` | `TIMESTAMP` | ISO-formatted transaction datetime | Strict chronological ordering and velocity/pass-through detection |
| `payment_mode` | `VARCHAR` | Channel: `UPI`, `IMPS`, `NEFT`, `RTGS` | Payment mode breakdown and channel-specific behavior |
| `narration` | `VARCHAR` | Free-text transaction remark | Untrusted input; analyzed as metadata, excluded from LLM prompts |
| `ip_address` | `VARCHAR` | IPv4 address of initiating transaction | IP reuse analysis across distinct accounts |
| `device_type` | `VARCHAR` | Client device identifier string (e.g. `Android`, `iOS`) | Device sharing analysis across distinct accounts |

---

## 2. Derived Analytical Entities

### A. Graph Nodes (`GraphNode`)
- `id`: Account identifier
- `label`: Display label
- `layer`: Distance from victim (`VICTIM`, `L1`, `L2`, `L3`, `L3+`)
- `risk_score`: Mule Risk Index (0–100)
- `tainted_amount`: Total estimated victim-origin money remaining in account
- `bank`: Bank abbreviation derived from IFSC prefix

### B. Graph Edges (`GraphEdge`)
- `source`: Sending account
- `target`: Receiving account
- `amount`: Total INR transfer amount
- `tainted_amount`: Calculated portion of victim-origin flow along this specific transfer
- `timestamp`: Transaction time
- `transaction_id`: Source record identifier
- `payment_mode`: Payment channel used

### C. Taint Result (`TaintResult`)
- `account_id`: Investigated account
- `tainted_amount`: Estimated victim-origin money residing in account
- `total_balance`: Total observed incoming balance
- `taint_ratio`: Proportional taint fraction ($\frac{\text{tainted\_amount}}{\text{total\_balance}}$)
- `warning`: Set to `"OPENING_BALANCE_UNKNOWN_OR_PRE_FUNDED"` if observed net balance was negative prior to dataset window

### D. Freeze Candidate (`FreezeCandidate`)
- `rank`: Priority rank for emergency preservation action (Rank 1 = highest impact)
- `account_id`: Account to freeze
- `bank`: Associated bank name
- `layer`: Hop distance from victim
- `tainted_amount_held`: Tainted balance held by account
- `estimated_blocked_amount`: Flow preserved by cutting this node
- `risk_score`: Analytical risk score (kept strictly separate from freeze ranking)
- `reason`: Mathematical explanation of why this account was selected

---

## 3. Feature Availability Matrix

| Feature | Status | Justification / Source |
|---|---|---|
| Money-flow Tracing (L1-L4) | **IMPLEMENTED** | Derived from `sender_account`, `receiver_account`, `amount`, `timestamp` |
| Proportional Taint Model | **IMPLEMENTED** | Calculated chronologically on transaction graph |
| Max-flow / Min-cut Freeze Engine | **IMPLEMENTED** | Computed using NetworkX on tainted capacity flow network |
| Mule Risk Index (0-100) | **IMPLEMENTED** | 8 deterministic features with documented weights |
| Cross-bank Analysis | **IMPLEMENTED** | Extracted from `sender_ifsc` and `receiver_ifsc` |
| IP / Device Reuse | **IMPLEMENTED** | Extracted from `ip_address` and `device_type` |
| Fund Cycles (Loops) | **IMPLEMENTED** | Detected via bounded NetworkX cycle traversal |
| Physical ATM / Cash-out | **UNAVAILABLE_FROM_DATASET** | Dataset does not contain cash withdrawal / ATM terminal columns |
| Cryptocurrency Wallets / Exchanges | **UNAVAILABLE_FROM_DATASET** | Dataset does not contain crypto wallet addresses or exchange tags |
| IP Geolocation / Country Mapping | **UNAVAILABLE_FROM_DATASET** | Country metadata is not packaged in the local CSV records |
