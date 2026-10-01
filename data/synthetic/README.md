# SYNTHETIC DATA — DEVELOPMENT ONLY

> ⚠️ **WARNING: This is SYNTHETIC / FABRICATED data created for development and testing.**
> It does NOT represent any real person, bank account, or financial transaction.
> It must NEVER be presented as real-world evidence.
> It is labelled: **DEVELOPMENT / SYNTHETIC DATA**

## Purpose
This dataset allows the system to be developed and tested before the real hackathon dataset arrives.

## Scenario
Victim (V001) transfers money that flows through 3 layers:
- L1: First-level receiving accounts (direct from victim)
- L2: Second-level mule accounts
- L3: Cash-out / terminal accounts

## Accounts
| Account | Role | Bank |
|---|---|---|
| ACC_V001 | Victim (source of fraud) | SBI |
| ACC_L1A | Layer 1 - Primary mule | HDFC |
| ACC_L1B | Layer 1 - Secondary mule | ICICI |
| ACC_L2A | Layer 2 - Mule | Axis |
| ACC_L2B | Layer 2 - Mule | Kotak |
| ACC_L2C | Layer 2 - Mule (cycle participant) | HDFC |
| ACC_L3A | Layer 3 - Cash-out terminal | Punjab National |
| ACC_L3B | Layer 3 - Cash-out terminal | Canara |
| ACC_L3C | Layer 3 - Cash-out terminal | BOI |
| ACC_EXT | External / unrelated account | SBI |

## Special cases included
- Rapid pass-through: ACC_L1A receives and sends within 4 minutes
- Cycle: ACC_L2C → ACC_L2B → ACC_L2C
- Multi-bank: transactions cross 6 different banks
- Fan-in: ACC_L2A receives from both L1A and L1B
- Fan-out: ACC_L1A sends to 3 different accounts
- Malicious narration: one transaction narration contains prompt injection text
- A case where freeze priority differs from risk ranking (ACC_L2B has moderate risk but holds most tainted money)
