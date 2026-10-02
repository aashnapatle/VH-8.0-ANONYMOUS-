# EXPLAINABLE MULE RISK INDEX METHODOLOGY

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Metric**: Mule Risk Score (0–100)  

---

## 1. Principles

1. **Deterministic & Reproducible**: Given the same dataset and account, the risk engine will always produce the exact same score. No random numbers, heuristic drift, or LLM hallucination.
2. **Explainable Reason Codes**: Every point added to the score is backed by a specific reason code, triggered threshold, and supporting transaction data.
3. **Risk is NOT Guilt**: The score represents an analytical risk indicator for decision support. It is not a legal verdict.

---

## 2. Risk Feature Definitions & Weights

The total score is bounded to $[0, 100]$:
$$\text{Score} = \min\left(100.0, \sum_{i} \text{Weight}_i \times \mathbb{I}(\text{Signal}_i \text{ triggered})\right)$$

| Signal Code | Weight | Trigger Threshold | Investigative Rationale |
|---|---|---|---|
| `RAPID_PASS_THROUGH` | **30** | $\ge 70\%$ of inflow exits within 10 minutes | Classic mule behavior: rapid movement prevents fund recovery |
| `HIGH_FAN_IN` | **15** | $\ge 5$ distinct sender accounts | Consolidation point / drop account receiving from multiple victims or mules |
| `HIGH_FAN_OUT` | **15** | $\ge 5$ distinct receiver accounts | Layering / dispersion account distributing funds to cash-out mules |
| `MULTI_HOP_MOVEMENT` | **15** | Account is at Hop 2 or deeper from victim | Multi-layered chain designed to obscure money trails |
| `CYCLE_DETECTED` | **10** | Participates in a circular fund loop ($A \to B \to C \to A$) | Obfuscation tactic to artificially inflate transaction volume |
| `CROSS_BANK_ACTIVITY` | **5** | Transactions span $\ge 3$ distinct bank codes | Inter-bank hops introduce inter-bank settlement delays |
| `DEVICE_OVERLAP` | **5** | Device shared across $\ge 3$ distinct accounts | Coordinated operation or shared bot infrastructure |
| `IP_OVERLAP` | **5** | IP address shared across $\ge 3$ distinct accounts | Coordinated botnet, proxy, or syndicate operation |
| **Total Max Weight** | **100** | — | — |

---

## 3. Risk Classification Labels

- `CRITICAL`: Score $\ge 80.0$
- `HIGH`: $60.0 \le \text{Score} < 80.0$
- `MEDIUM`: $35.0 \le \text{Score} < 60.0$
- `LOW`: $\text{Score} < 35.0$

---

## 4. Separation: Risk Score vs. Freeze Priority

| Attribute | Risk Score | Freeze Priority |
|---|---|---|
| **Core Question** | *"How suspicious is this account's behavior?"* | *"Freezing which accounts preserves the maximum victim money right now?"* |
| **Driven By** | Behavioral network patterns & velocity | Remaining tainted flow volume & graph cut bottlenecks |
| **Example Scenario** | An L1 mule that has already emptied its balance has high risk (100) but 0 freeze priority. | An L2 account holding ₹500,000 of victim taint may have moderate risk (45) but is the #1 Freeze Priority. |
