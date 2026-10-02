"""
config.py — Abhedya-Chakra Configuration

All thresholds and weights are documented here.
Never hide weights inside service code.

STATUS: IMPLEMENTED
"""
from pathlib import Path

# ─── Project Paths ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
REAL_PARQUET = PROCESSED_DATA_DIR / "transactions.parquet"
REAL_CSV = Path(r"C:\Users\anany\Downloads\VoidHacks8_MuleAccount_2M_Transactions.csv")
SYNTHETIC_CSV = DATA_DIR / "synthetic" / "transactions.csv"
DUCKDB_PATH = BASE_DIR / "data" / "abhedya.duckdb"

# ─── Graph Settings ──────────────────────────────────────────────────────────
MAX_HOPS = 4                   # Maximum traversal depth for money-flow tracing
SUBGRAPH_LIMIT = 500           # Max nodes in a subgraph before we warn

# ─── Detection Thresholds ────────────────────────────────────────────────────
# These are investigative signals, NOT proof of crime.

# Fan-in: how many distinct senders triggers HIGH_FAN_IN
FAN_IN_THRESHOLD = 5

# Fan-out: how many distinct receivers triggers HIGH_FAN_OUT
FAN_OUT_THRESHOLD = 5

# Pass-through: what fraction (0-1) of inflow exiting quickly triggers RAPID_PASS_THROUGH
PASS_THROUGH_RATIO = 0.70      # 70% of inflow exits within PASS_THROUGH_WINDOW
PASS_THROUGH_WINDOW_MINUTES = 10

# Cross-bank: how many distinct banks triggers CROSS_BANK_ACTIVITY
CROSS_BANK_THRESHOLD = 3

# Cycle detection: enabled by default
CYCLE_DETECTION_ENABLED = True

# Device overlap: same device across 3+ accounts signals DEVICE_OVERLAP
DEVICE_OVERLAP_THRESHOLD = 3

# IP overlap: same IP across 3+ accounts signals IP_OVERLAP
IP_OVERLAP_THRESHOLD = 3

# ─── Risk Score Weights ──────────────────────────────────────────────────────
# These weights sum to 100 (max score = 100).
# Each signal contributes its weight when fully triggered.
# Documented formula: score = sum(weight_i * signal_i) capped at 100

RISK_WEIGHTS = {
    "HIGH_FAN_IN":          15,  # Many senders → possible drop-point
    "HIGH_FAN_OUT":         15,  # Many receivers → possible distributor
    "RAPID_PASS_THROUGH":   30,  # Rapid in-and-out → strong mule signal
    "MULTI_HOP_MOVEMENT":   15,  # Part of multi-hop chain
    "CYCLE_DETECTED":       10,  # In a cycle → obfuscation attempt
    "CROSS_BANK_ACTIVITY":   5,  # Cross-bank → harder to trace
    "DEVICE_OVERLAP":        5,  # Same device → coordination signal
    "IP_OVERLAP":            5,  # Same IP → coordination signal
}

# Risk label thresholds
RISK_LABELS = {
    "CRITICAL": 80,
    "HIGH":     60,
    "MEDIUM":   35,
    "LOW":       0,
}

# ─── Taint Model ─────────────────────────────────────────────────────────────
# Model: PROPORTIONAL TAINT
# Formula: tainted_out = transfer_amount * (tainted_balance / total_balance)
# This is an approximation for investigative support only.
# It does NOT represent forensic-legal standard of victim-origin tracing.
TAINT_MODEL = "proportional"   # "proportional" or "fifo" (only proportional implemented)

# ─── Freeze Engine ───────────────────────────────────────────────────────────
# Method: max-flow / min-cut on tainted-balance graph
# Source: victim account
# Sink: terminal/cash-out nodes (accounts with no outgoing in subgraph)
# Edge capacity: tainted amount flowing through that edge
FREEZE_METHOD = "max_flow_min_cut"

# ─── AI Settings ─────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"      # or any locally available model
AI_ENABLED = True              # Set False if Ollama not available
AI_MAX_RETRIES = 2             # Retry on validation failure
AI_TIMEOUT_SECONDS = 30

# ─── Report Settings ─────────────────────────────────────────────────────────
REPORT_OUTPUT_DIR = BASE_DIR / "data" / "reports"
