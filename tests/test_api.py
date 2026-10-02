"""
test_api.py — End-to-end API integration tests

Tests all FastAPI routes:
- /health
- /
- /api/accounts
- /api/accounts/{account_id}
- /api/transactions/{account_id}
- /api/investigate/{account_id}
- /api/graph/{account_id}
- /api/evidence/{account_id}
- /api/judge/demo
- /api/benchmark
- /api/reports/{account_id}
- /api/ai/narrative/{account_id}

STATUS: IMPLEMENTED
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import SYNTHETIC_CSV, REAL_PARQUET
from backend.db.loader import reset_and_reload, reset_and_reload_parquet

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    reset_and_reload(SYNTHETIC_CSV)
    yield
    if REAL_PARQUET.exists():
        reset_and_reload_parquet(REAL_PARQUET)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Abhedya-Chakra" in data["service"]


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "/docs" in data["docs"]


def test_list_accounts():
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert "accounts" in data
    assert "ACC_V001" in data["accounts"]


def test_get_account_valid():
    response = client.get("/api/accounts/ACC_V001")
    assert response.status_code == 200
    data = response.json()
    assert data["account_id"] == "ACC_V001"
    assert data["total_sent"] > 0
    assert data["transaction_count"] > 0


def test_get_account_not_found():
    response = client.get("/api/accounts/ACC_NONEXISTENT_999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_account_invalid_id():
    response = client.get("/api/accounts/" + "A" * 150)
    assert response.status_code == 400


def test_get_transactions_valid():
    response = client.get("/api/transactions/ACC_V001")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for tx in data:
        assert "transaction_id" in tx
        assert "amount" in tx


def test_get_transactions_not_found():
    response = client.get("/api/transactions/ACC_NONEXISTENT_999")
    assert response.status_code == 404


def test_investigate_valid():
    response = client.get("/api/investigate/ACC_V001?max_hops=3")
    assert response.status_code == 200
    data = response.json()
    assert data["victim_account"] == "ACC_V001"
    assert "account" in data
    assert "risk" in data
    assert "graph" in data
    assert "timeline" in data
    assert "evidence" in data
    assert "taint" in data
    assert "freeze_plan" in data

    # Verify graph structure
    assert len(data["graph"]["nodes"]) > 0
    assert len(data["graph"]["edges"]) > 0

    # Verify freeze plan
    assert len(data["freeze_plan"]["freeze_candidates"]) > 0
    assert data["freeze_plan"]["total_estimated_recoverable"] >= 0

    # Verify timeline is sorted
    timeline = data["timeline"]
    assert len(timeline) > 0
    for event in timeline:
        assert "timestamp" in event
        assert "description" in event


def test_investigate_not_found():
    response = client.get("/api/investigate/ACC_NONEXISTENT_999")
    assert response.status_code == 404


def test_graph_endpoint_valid():
    response = client.get("/api/graph/ACC_V001")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


def test_evidence_endpoint_valid():
    response = client.get("/api/evidence/ACC_V001")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    types = {item["evidence_type"] for item in data}
    assert "transaction" in types


def test_judge_demo():
    response = client.get("/api/judge/demo")
    assert response.status_code == 200
    data = response.json()
    assert data["demo_victim"] == "ACC_V001"
    assert "performance" in data
    assert "investigation_ms" in data["performance"]
    assert "investigation" in data


def test_benchmark():
    response = client.get("/api/benchmark")
    assert response.status_code == 200
    data = response.json()
    assert "measured" in data
    assert "targets" in data
    assert data["measured"]["accounts_in_subgraph"] > 0


def test_generate_report_pdf():
    response = client.post("/api/reports/ACC_V001")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 1000  # Valid PDF is several KB


def test_ai_narrative_endpoint():
    response = client.post("/api/ai/narrative/ACC_V001")
    assert response.status_code == 200
    data = response.json()
    assert data["account_id"] == "ACC_V001"
    assert "narrative" in data
    assert len(data["narrative"]) > 50
    assert "injection_resistance_demo" in data
    assert data["injection_resistance_demo"]["test"] == "prompt_injection_resistance"
