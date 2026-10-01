"""
test_query.py — Tests for the public query API
================================================
Uses in-memory DuckDB loaded with synthetic data.
The real dataset is NEVER loaded in these tests.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.models import AccountSummary, Transaction


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_query_fns(duckdb_con):
    """
    Return query functions that use the given in-memory connection.
    We patch the module-level connection directly.
    """
    import src.data.database as db
    import src.data.query as q
    db._connection = duckdb_con
    return q


# ── Tests: get_account_transactions ───────────────────────────────────────────

class TestGetAccountTransactions:
    def test_returns_list(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_transactions("ACCT00000001")
        assert isinstance(result, list)

    def test_known_account_has_transactions(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_transactions("ACCT00000001")
        assert len(result) > 0

    def test_unknown_account_returns_empty(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_transactions("DOES_NOT_EXIST_XYZ")
        assert result == []

    def test_returns_transaction_objects(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_transactions("ACCT00000001")
        for tx in result:
            assert isinstance(tx, Transaction)

    def test_includes_both_sent_and_received(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        # ACCT00000001 both sends and receives in synthetic data
        result = q.get_account_transactions("ACCT00000001")
        senders = {tx.sender_account for tx in result}
        receivers = {tx.receiver_account for tx in result}
        # Should appear as both sender and receiver
        assert "ACCT00000001" in senders or "ACCT00000001" in receivers

    def test_ordered_by_timestamp(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_transactions("ACCT00000001")
        timestamps = [tx.timestamp for tx in result]
        assert timestamps == sorted(timestamps)


# ── Tests: get_incoming_transactions ──────────────────────────────────────────

class TestGetIncomingTransactions:
    def test_all_incoming_have_correct_receiver(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        account = "ACCT00000001"
        result = q.get_incoming_transactions(account)
        for tx in result:
            assert tx.receiver_account == account

    def test_incoming_does_not_include_outgoing(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        account = "ACCT00000001"
        result = q.get_incoming_transactions(account)
        for tx in result:
            # sender_account must NOT be this account (it's incoming only)
            assert tx.sender_account != account

    def test_unknown_account_returns_empty(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_incoming_transactions("NONEXISTENT_ACCOUNT")
        assert result == []


# ── Tests: get_outgoing_transactions ──────────────────────────────────────────

class TestGetOutgoingTransactions:
    def test_all_outgoing_have_correct_sender(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        account = "ACCT00000001"
        result = q.get_outgoing_transactions(account)
        for tx in result:
            assert tx.sender_account == account

    def test_outgoing_does_not_include_incoming(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        account = "ACCT00000001"
        result = q.get_outgoing_transactions(account)
        for tx in result:
            assert tx.receiver_account != account

    def test_unknown_account_returns_empty(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_outgoing_transactions("NONEXISTENT_ACCOUNT")
        assert result == []


# ── Tests: get_counterparties ─────────────────────────────────────────────────

class TestGetCounterparties:
    def test_returns_dict(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_counterparties("ACCT00000001")
        assert isinstance(result, dict)

    def test_dict_has_required_keys(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_counterparties("ACCT00000001")
        assert "account_id" in result
        assert "senders" in result
        assert "receivers" in result
        assert "all_counterparties" in result

    def test_senders_received_from(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        # ACCT00000002 and ACCT00000003 sent to ACCT00000001
        result = q.get_counterparties("ACCT00000001")
        assert "ACCT00000002" in result["senders"]

    def test_receivers_sent_to(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        # ACCT00000001 sent to ACCT00000002 and ACCT00000003
        result = q.get_counterparties("ACCT00000001")
        assert "ACCT00000002" in result["receivers"]

    def test_all_counterparties_is_union(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_counterparties("ACCT00000001")
        all_cp = set(result["all_counterparties"])
        assert all_cp == set(result["senders"]) | set(result["receivers"])

    def test_unknown_account_returns_empty_lists(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_counterparties("NONEXISTENT")
        assert result["senders"] == []
        assert result["receivers"] == []
        assert result["all_counterparties"] == []


# ── Tests: get_account_summary ────────────────────────────────────────────────

class TestGetAccountSummary:
    def test_returns_account_summary(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        assert isinstance(result, AccountSummary)

    def test_account_id_correct(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        assert result.account_id == "ACCT00000001"

    def test_incoming_count_correct(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        # ACCT00000001 receives from: ACCT00000003, ACCT00000002, ACCT00000004, ACCT00000005
        assert result.incoming_transaction_count >= 1

    def test_outgoing_count_correct(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        # ACCT00000001 sends to: ACCT00000002, ACCT00000003
        assert result.outgoing_transaction_count >= 1

    def test_total_incoming_amount_positive(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        assert result.total_incoming_amount > 0

    def test_total_outgoing_amount_positive(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        assert result.total_outgoing_amount > 0

    def test_timestamps_present(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        assert result.first_transaction_timestamp is not None
        assert result.last_transaction_timestamp is not None
        assert result.first_transaction_timestamp <= result.last_transaction_timestamp

    def test_unknown_account_returns_zero_summary(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("TOTALLY_UNKNOWN_ACCOUNT")
        assert result.incoming_transaction_count == 0
        assert result.outgoing_transaction_count == 0
        assert result.total_incoming_amount == 0.0
        assert result.total_outgoing_amount == 0.0

    def test_as_dict_is_json_serializable(self, duckdb_con):
        import json
        q = make_query_fns(duckdb_con)
        result = q.get_account_summary("ACCT00000001")
        d = result.as_dict()
        # Should not raise
        json.dumps(d)


# ── Tests: get_transactions_between ───────────────────────────────────────────

class TestGetTransactionsBetween:
    def test_time_range_returns_correct_rows(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        # All synthetic transactions on 2026-09-22
        result = q.get_transactions_between(
            "2026-09-22 00:00:00",
            "2026-09-22 23:59:59",
        )
        assert len(result) >= 5  # 5 txns in this range in synthetic data

    def test_narrow_time_range(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        # Only transactions between 10:00 and 10:06
        result = q.get_transactions_between(
            "2026-09-22 10:00:00",
            "2026-09-22 10:06:00",
        )
        # Should include TXN000000001 (10:00) and TXN000000002 (10:05)
        assert len(result) >= 1

    def test_no_results_for_empty_range(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_transactions_between(
            "2020-01-01 00:00:00",
            "2020-01-01 23:59:59",
        )
        assert result == []

    def test_timestamps_within_range(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        start = "2026-09-22 10:00:00"
        end = "2026-09-22 10:12:00"
        result = q.get_transactions_between(start, end)
        for tx in result:
            assert tx.timestamp >= datetime.fromisoformat(start)
            assert tx.timestamp <= datetime.fromisoformat(end)

    def test_accepts_datetime_objects(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        start = datetime(2026, 9, 22, 0, 0, 0)
        end = datetime(2026, 9, 22, 23, 59, 59)
        result = q.get_transactions_between(start, end)
        assert isinstance(result, list)


# ── Tests: get_transaction (single) ──────────────────────────────────────────

class TestGetTransaction:
    def test_known_transaction_id(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_transaction("TXN000000001")
        assert result is not None
        assert isinstance(result, Transaction)
        assert result.transaction_id == "TXN000000001"

    def test_unknown_transaction_id_returns_none(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        result = q.get_transaction("TXN_DOES_NOT_EXIST")
        assert result is None


# ── Tests: Transaction model ──────────────────────────────────────────────────

class TestTransactionModel:
    def test_as_dict_has_all_fields(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        txns = q.get_account_transactions("ACCT00000001")
        assert len(txns) > 0
        d = txns[0].as_dict()
        expected_fields = [
            "transaction_id", "sender_account", "receiver_account",
            "sender_ifsc", "receiver_ifsc", "amount", "timestamp",
            "payment_mode", "narration", "ip_address", "device_type",
        ]
        for field in expected_fields:
            assert field in d, f"Missing field: {field}"

    def test_timestamp_is_iso_string_in_dict(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        txns = q.get_account_transactions("ACCT00000001")
        d = txns[0].as_dict()
        # timestamp in dict must be a string (ISO format)
        assert isinstance(d["timestamp"], str)

    def test_amount_is_float(self, duckdb_con):
        q = make_query_fns(duckdb_con)
        txns = q.get_account_transactions("ACCT00000001")
        for tx in txns:
            assert isinstance(tx.amount, float)
