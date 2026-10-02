# TAINT PROPAGATION METHODOLOGY

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Model**: Proportional Taint Propagation (Water-Mixing Model)  

---

## 1. Core Model Formulation

In real-world multi-hop financial fraud, funds from victims mix with legitimate or other fraudulent deposits in intermediate accounts. Abhedya-Chakra models money taint using the **Proportional Taint Model**:

$$\text{Taint Ratio}(u) = \min\left(1.0, \frac{\text{Tainted Balance}(u)}{\text{Total Inflow}(u)}\right)$$

$$\text{Tainted Outflow}(u \xrightarrow{\text{tx}} v) = \text{Amount}(\text{tx}) \times \text{Taint Ratio}(u)$$

### Step-by-Step Example
1. **Victim Account $V$** sends ₹100,000 to Account $A$.
   - Tainted Balance of $A$ = ₹100,000.
   - Total Inflow of $A$ = ₹100,000.
   - $\text{Taint Ratio}(A) = 1.0$ (100%).
2. **Account $A$** receives ₹100,000 from an unrelated third party.
   - Total Balance of $A$ = ₹200,000.
   - Tainted Balance of $A$ = ₹100,000.
   - $\text{Taint Ratio}(A) = \frac{100,000}{200,000} = 0.50$ (50%).
3. **Account $A$** transfers ₹60,000 to Account $B$.
   - $\text{Tainted Outflow}(A \to B) = 60,000 \times 0.50 = \text{₹}30,000$.
   - Account $B$ receives ₹60,000 total, of which ₹30,000 is victim-origin taint.

---

## 2. Strict Chronological Ordering

Transactions are processed in strict **timestamp ascending** order:
1. When computing an account's observed balance and taint ratio, only inflows that occurred *before or at* the transfer time are considered.
2. If multiple transactions share the exact same timestamp, a secondary deterministic ordering (`transaction_id ASC`) is enforced.

---

## 3. Handling Observation Window Limitations

Financial transaction datasets often capture a temporal slice (e.g., a 2-week window). An account may send funds that were deposited before the window began.

- **Observed Balance Formula**:
  $$\text{Observed Balance} = \text{Observed Inflow} - \text{Observed Outflow}$$
- **Negative Balance Handling**:
  If $\text{Observed Balance} < 0$, the engine:
  1. Attaches the tag: `"OPENING_BALANCE_UNKNOWN_OR_PRE_FUNDED"` to the account's `TaintResult`.
  2. Floors the observed tracking balance at `0.0` to maintain arithmetic stability without making false assumptions about prior history.

---

## 4. Cross-Service Consistency

The same tainted amount is strictly maintained across all reporting layers:
- `graph.edges[i].tainted_amount`
- `timeline[i].tainted_amount`
- `transaction_chain[i].tainted_amount`
- `evidence[i].tainted_amount`
- PDF Investigation Report
