# FREEZE PRIORITY ENGINE METHODOLOGY

**Project**: Operation Abhedya-Chakra — Freeze-First  
**Method**: Max-Flow / Min-Cut on Tainted Capacity Flow Graph  

---

## 1. Objective: Freeze-First

In cyber fraud investigations, the first 30–60 minutes are critical. Freezing every account in a 500-node network is legally and operationally impossible. 

The Freeze Priority Engine answers:
> *"Which specific accounts should the authorized officer freeze first to preserve the maximum volume of victim-origin funds before they reach cash-out points?"*

---

## 2. Mathematical Formulation

1. **Capacity Construction**:
   Construct a directed flow network $G' = (V', E')$ where each edge capacity $c(u, v)$ represents the **tainted amount** flowing from $u$ to $v$:
   $$c(u, v) = \text{Amount}(u \to v) \times \text{Taint Ratio}(u)$$

2. **Sink Identification**:
   Terminal nodes (accounts with out-degree = 0 in the subgraph) represent exit / cash-out endpoints. A virtual `__SUPER_SINK__` $T$ is connected from all terminal sinks.

3. **Minimum Cut Calculation**:
   Using the Ford-Fulkerson / Edmonds-Karp max-flow theorem:
   $$\text{Max Flow}(S \to T) = \text{Min Cut}(S \to T)$$
   The min-cut partition $(S_{\text{reach}}, S_{\text{non-reach}})$ reveals the exact bottleneck accounts whose removal severs the largest volume of tainted money flow.

4. **Candidate Ranking**:
   Accounts are ranked primarily by $\text{Estimated Blocked Amount} \downarrow$, accompanied by their bank name, IFSC, layer distance, and tainted balance held.

---

## 3. Decision Support Safeguards

- **No Automated Execution**: The engine produces decision-support recommendations only. No automated freeze requests or banking API calls are made without human authorization.
- **Explainability**: Every freeze candidate includes an explicit mathematical justification explaining how much victim money is preserved by freezing that specific account.
