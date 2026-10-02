"""
schemas.py — Pydantic response models (shared data contract)

These define exactly what the API returns.
Frontend (Shreya) and backend (Ananya) both follow these schemas.
Ground-truth aligned for 2M local transaction dataset.

STATUS: IMPLEMENTED
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Data Source ─────────────────────────────────────────────────────────────

class DataSourceInfo(BaseModel):
    type: str = "LOCAL_SUPPLIED_DATASET"
    dataset_rows: int = 1997748
    dataset_date_range: Dict[str, str] = Field(default_factory=lambda: {
        "from": "2026-09-15 00:00:00",
        "to": "2026-09-29 23:59:58"
    })
    source_file: str = "VoidHacks8_MuleAccount_2M_Transactions.csv"


# ─── Transaction ─────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    transaction_id: str
    sender_account: str
    receiver_account: str
    sender_ifsc: Optional[str] = None
    receiver_ifsc: Optional[str] = None
    amount: float
    timestamp: str
    payment_mode: Optional[str] = None
    narration: Optional[str] = None   # RAW — never forward to LLM
    ip_address: Optional[str] = None
    device_type: Optional[str] = None


# ─── Account ─────────────────────────────────────────────────────────────────

class AccountSummary(BaseModel):
    account_id: str
    total_received: float
    total_sent: float
    net_balance: float
    transaction_count: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    banks: List[str] = []
    layer: Optional[str] = None      # VICTIM, L1, L2, L3


# ─── Graph ───────────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    layer: str                       # VICTIM, L1, L2, L3, UNKNOWN
    risk_score: Optional[float] = None
    tainted_amount: Optional[float] = None
    bank: Optional[str] = None

class GraphEdge(BaseModel):
    source: str
    target: str
    amount: float
    tainted_amount: Optional[float] = None
    timestamp: str
    transaction_id: str
    payment_mode: Optional[str] = None
    sender_ifsc: Optional[str] = None
    receiver_ifsc: Optional[str] = None

class GraphData(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


# ─── Transaction Chain ───────────────────────────────────────────────────────

class TransactionChainItem(BaseModel):
    hop: int
    from_account: str
    to_account: str
    transaction_id: str
    amount: float
    tainted_amount: float
    timestamp: str
    payment_mode: Optional[str] = None
    sender_ifsc: Optional[str] = None
    receiver_ifsc: Optional[str] = None


# ─── Categorical & Metadata Analyses ─────────────────────────────────────────

class PaymentModeSummary(BaseModel):
    payment_mode: str
    transaction_count: int
    total_amount: float

class IPAnalysis(BaseModel):
    unique_ips: int
    reused_ips_count: int
    ip_country: str = "UNAVAILABLE"
    details: List[Dict[str, Any]] = []
    note: str = "Country geolocation is UNAVAILABLE_FROM_DATASET in local records."

class DeviceAnalysis(BaseModel):
    unique_devices: int
    reused_devices_count: int
    details: List[Dict[str, Any]] = []

class CrossBankAnalysis(BaseModel):
    unique_banks: int
    banks: List[str] = []
    cross_bank_transfers_count: int = 0
    details: List[Dict[str, Any]] = []

class CycleAnalysis(BaseModel):
    cycle_detected: bool
    cycle_count: int
    cycles_found: List[List[str]] = []

class FeatureStatus(BaseModel):
    status: str = "UNAVAILABLE_FROM_DATASET"
    reason: str


# ─── Detection ───────────────────────────────────────────────────────────────

class DetectionSignal(BaseModel):
    code: str                        # e.g. "HIGH_FAN_IN"
    triggered: bool
    detail: str
    value: Optional[float] = None


# ─── Risk ────────────────────────────────────────────────────────────────────

class RiskReason(BaseModel):
    code: str
    detail: str
    weight: int

class RiskScore(BaseModel):
    account_id: str
    score: float                     # 0–100
    label: str                       # LOW / MEDIUM / HIGH / CRITICAL
    reasons: List[RiskReason]
    disclaimer: str = (
        "Risk score is an analytical investigative signal. "
        "It is NOT proof of criminal activity."
    )


# ─── Taint ───────────────────────────────────────────────────────────────────

class TaintResult(BaseModel):
    account_id: str
    tainted_amount: float            # Victim-origin money still in this account
    total_balance: float             # Total balance computed from transactions
    taint_ratio: float               # tainted / total (0.0–1.0)
    model_used: str = "proportional"
    warning: Optional[str] = None    # Set if opening balance is unknown/pre-funded
    disclaimer: str = (
        "Taint amounts are approximate (proportional model). "
        "Not suitable as standalone forensic evidence."
    )


# ─── Freeze Plan ─────────────────────────────────────────────────────────────

class FreezeCandidate(BaseModel):
    rank: int
    account_id: str
    bank: str
    ifsc: Optional[str] = None
    layer: Optional[str] = None
    tainted_amount_held: float
    estimated_blocked_amount: float
    risk_score: Optional[float] = None
    reason: str

class FreezePlan(BaseModel):
    freeze_candidates: List[FreezeCandidate]
    total_estimated_recoverable: float
    method: str
    disclaimer: str = (
        "This is a decision-support recommendation for authorized investigators only. "
        "The system does NOT execute any actual freeze operations."
    )


# ─── Evidence ────────────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    evidence_type: str               # transaction / graph_relationship / risk_reason / taint / freeze
    transaction_id: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    amount: Optional[float] = None
    tainted_amount: Optional[float] = None
    timestamp: Optional[str] = None
    ifsc_sender: Optional[str] = None
    ifsc_receiver: Optional[str] = None
    payment_mode: Optional[str] = None
    rule_triggered: Optional[str] = None
    graph_relationship: Optional[str] = None
    detail: Optional[str] = None


# ─── Timeline ────────────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    timestamp: str
    event_type: str                  # TRANSFER / DETECTION / RISK_FLAG / FREEZE_CANDIDATE
    description: str
    account_from: Optional[str] = None
    account_to: Optional[str] = None
    amount: Optional[float] = None
    tainted_amount: Optional[float] = None
    transaction_id: Optional[str] = None
    payment_mode: Optional[str] = None


# ─── Full Investigation Response ─────────────────────────────────────────────

class InvestigationResponse(BaseModel):
    victim_account: str
    investigated_at: str
    data_source: DataSourceInfo = Field(default_factory=DataSourceInfo)
    account: AccountSummary
    risk: RiskScore
    graph: GraphData
    transaction_chain: List[TransactionChainItem] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    taint: TaintResult
    freeze_plan: FreezePlan
    payment_mode_summary: List[PaymentModeSummary] = Field(default_factory=list)
    ip_analysis: Optional[IPAnalysis] = None
    device_analysis: Optional[DeviceAnalysis] = None
    cross_bank_analysis: Optional[CrossBankAnalysis] = None
    cycle_analysis: Optional[CycleAnalysis] = None
    cash_out_analysis: FeatureStatus = Field(default_factory=lambda: FeatureStatus(
        status="UNAVAILABLE_FROM_DATASET",
        reason="No explicit cash-out/ATM indicator in dataset records."
    ))
    crypto_analysis: FeatureStatus = Field(default_factory=lambda: FeatureStatus(
        status="UNAVAILABLE_FROM_DATASET",
        reason="No crypto wallet or exchange indicators in dataset records."
    ))
    data_label: str = "LOCAL_SUPPLIED_DATASET — Ground Truth Investigation"
