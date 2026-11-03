"""Tests for db/sql_client.py, the local SQLite replacement for the old
Firestore client - covers the behaviors every caller actually depends on:
merge-upsert semantics, status-equality polling, limit/orderBy, timestamp
range queries, and auto-generated ids.
"""
import time

import pytest

from db.sql_client import SQLiteClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "SQLITE_DB_PATH", tmp_path / "test.db")
    return SQLiteClient()


def test_enabled_on_a_fresh_temp_file(client):
    assert client.enabled is True


def test_write_now_merge_preserves_untouched_fields(client):
    client._write_now("signals", "J1", {"activeLane": "lane1", "phase": "green", "mode": "adaptive"}, merge=True)
    client._write_now("signals", "J1", {"phase": "yellow"}, merge=True)
    doc = client.get_doc("signals", "J1")
    assert doc["activeLane"] == "lane1"
    assert doc["phase"] == "yellow"
    assert doc["mode"] == "adaptive"


def test_write_now_without_merge_replaces_the_whole_document(client):
    client._write_now("signals", "J1", {"activeLane": "lane1", "phase": "green"}, merge=True)
    client._write_now("signals", "J1", {"phase": "red"}, merge=False)
    doc = client.get_doc("signals", "J1")
    assert "activeLane" not in doc
    assert doc["phase"] == "red"


def test_get_doc_missing_returns_none(client):
    assert client.get_doc("signals", "nope") is None


def test_read_pending_filters_by_status(client):
    client._write_now("commands", "cmd1", {"status": "pending", "type": "force_green"}, merge=True)
    client._write_now("commands", "cmd2", {"status": "done", "type": "release"}, merge=True)
    pending = client.read_pending("commands")
    assert [p["id"] for p in pending] == ["cmd1"]


def test_read_pending_custom_value(client):
    client._write_now("accidents", "a1", {"status": "resolving"}, merge=True)
    client._write_now("accidents", "a2", {"status": "active"}, merge=True)
    resolving = client.read_pending("accidents", value="resolving")
    assert [r["id"] for r in resolving] == ["a1"]


def test_list_docs_respects_limit_and_order(client):
    for i, ts in enumerate([100.0, 300.0, 200.0]):
        client._write_now("alerts", f"a{i}", {"message": f"m{i}", "timestamp": ts}, merge=False)
    newest_first = client.list_docs("alerts", limit=2, order_by_ts="desc")
    assert [d["timestamp"] for d in newest_first] == [300.0, 200.0]


def test_query_range_is_half_open(client):
    for ts in (50.0, 100.0, 150.0, 200.0):
        client._write_now("violations", None, {"timestamp": ts}, merge=False)
    ranged = client.query_range("violations", 100.0, 200.0)
    assert sorted(d["timestamp"] for d in ranged) == [100.0, 150.0]


def test_list_all_ignores_limit(client):
    for i in range(5):
        client._write_now("metrics", f"J1_2026-10-{i:02d}", {"avgWaitAdaptiveS": i}, merge=False)
    assert len(client.list_all("metrics")) == 5


def test_auto_generated_ids_are_unique(client):
    id1 = client._write_now("alerts", None, {"message": "a"}, merge=False)
    id2 = client._write_now("alerts", None, {"message": "b"}, merge=False)
    assert id1 != id2
    assert len(id1) == 32  # uuid4().hex


def test_delete_doc(client):
    client._write_now("accidents", "a1", {"status": "active"}, merge=True)
    client.delete_doc("accidents", "a1")
    assert client.get_doc("accidents", "a1") is None


def test_enqueue_async_write_lands_via_background_thread(client):
    client.write_signal("J2", {"activeLane": "lane2", "phase": "green", "mode": "adaptive"})
    deadline = time.time() + 2.0
    doc = None
    while time.time() < deadline:
        doc = client.get_doc("signals", "J2")
        if doc:
            break
        time.sleep(0.02)
    assert doc is not None and doc["activeLane"] == "lane2"


def test_disabled_client_is_a_safe_no_op(monkeypatch, tmp_path):
    import config
    # Point at a path whose parent can't be created, forcing _init_db to fail.
    monkeypatch.setattr(config, "SQLITE_DB_PATH", tmp_path / "nested" / "deep" / "x.db")
    monkeypatch.setattr("pathlib.Path.mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    c = SQLiteClient()
    assert c.enabled is False
    assert c.read_pending("commands") == []
    assert c.get_doc("signals", "J1") is None
    c.write_signal("J1", {"phase": "green"})  # must not raise
