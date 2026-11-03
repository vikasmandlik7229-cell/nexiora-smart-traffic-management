"""SQLite-backed replacement for the old Firestore client (backend/firebase/
db.py), removing the cloud dependency and its daily write quota entirely.

One generic `documents` table holds every "collection" from the original
Firestore-based design (junctions, signals, live_counts, violations, ...).
Each document is a JSON blob in the `data` column; `status` and `ts` are
denormalized copies of the two kinds of fields anything actually filters or
sorts by (read_pending's status-equality polling, and daily_report.py's
timestamp-range queries) - kept as real columns so those queries use normal
SQL indexes instead of scanning JSON.

Keeps the exact same public method names/signatures as the old
FirestoreClient (write_signal, add_alert, read_pending, get_client(), the
background-queue writer thread, ...) so the ~16 backend modules that call
them don't need to change - only their import line does. A handful of call
sites used Firestore's chainable `._db.collection(...).get()/.stream()` API
directly instead of a named method; those are rewritten (separately, not
here) to use the new get_doc/list_docs/list_all/query_range methods below.
"""
import json
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    id         TEXT NOT NULL,
    data       TEXT NOT NULL,
    status     TEXT,
    ts         REAL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (collection, id)
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(collection, status);
CREATE INDEX IF NOT EXISTS idx_documents_ts ON documents(collection, ts);
"""

# Different collections use different business-timestamp field names
# (CLAUDE.md section 7's data model) - checked in this order and copied into
# the one shared `ts` column. Each document only ever has one of these.
_TS_FIELDS = ("timestamp", "startedAt", "detectedAt")


class SQLiteClient:
    def __init__(self):
        self.enabled = False
        self._conn = None
        self._lock = threading.Lock()
        self._queue: "queue.Queue" = queue.Queue()
        self._init_db()
        if self.enabled:
            threading.Thread(target=self._writer_loop, daemon=True).start()
            print(f"Database: local SQLite at {config.SQLITE_DB_PATH} - no daily write quota.")

    def _init_db(self):
        try:
            path = Path(config.SQLITE_DB_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self.enabled = True
        except Exception as e:
            print(f"Database: initialisation failed ({e}) - running OFFLINE (writes are no-ops).")

    # ------------------------------------------------------------------
    # Write path: background queue -> single writer thread, same shape as
    # the old FirestoreClient (decouples callers from write latency).
    # ------------------------------------------------------------------
    def _writer_loop(self):
        while True:
            collection, doc_id, data, merge = self._queue.get()
            try:
                self._write_now(collection, doc_id, data, merge)
            except Exception as e:
                print(f"SQLite write to '{collection}' failed: {e}")

    def _write_now(self, collection: str, doc_id, data: dict, merge: bool) -> str:
        doc_id = doc_id or uuid.uuid4().hex
        with self._lock:
            if merge:
                row = self._conn.execute(
                    "SELECT data FROM documents WHERE collection=? AND id=?", (collection, doc_id)
                ).fetchone()
                if row:
                    existing = json.loads(row[0])
                    existing.update(data)
                    data = existing
            status = data.get("status")
            ts = next((data[f] for f in _TS_FIELDS if data.get(f) is not None), None)
            self._conn.execute(
                """INSERT INTO documents (collection, id, data, status, ts, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(collection, id) DO UPDATE SET
                     data=excluded.data, status=excluded.status, ts=excluded.ts, updated_at=excluded.updated_at""",
                (collection, doc_id, json.dumps(data), status, ts, data.get("updatedAt", time.time())),
            )
            self._conn.commit()
        return doc_id

    def _enqueue(self, collection: str, doc_id, data: dict, merge: bool = True):
        if not self.enabled:
            return
        data = dict(data)
        data.setdefault("updatedAt", time.time())
        self._queue.put((collection, doc_id, data, merge))

    def create_doc(self, collection: str, data: dict) -> str:
        """Synchronous create with an auto-generated id, returned
        immediately - for the few call sites that need the new id right
        away (e.g. ambulance_sim.py polling the request it just created),
        unlike every other write method which is fire-and-forget via the
        background queue. Returns "" if the database is offline."""
        if not self.enabled:
            return ""
        data = dict(data)
        data.setdefault("updatedAt", time.time())
        return self._write_now(collection, None, data, merge=False)

    # ------------------------------------------------------------------
    # One method per collection - identical names/signatures to the old
    # FirestoreClient (CLAUDE.md section 7).
    # ------------------------------------------------------------------
    def write_junction(self, junction_id: str, data: dict):
        self._enqueue("junctions", junction_id, data)

    def write_road(self, road_id: str, data: dict):
        self._enqueue("roads", road_id, data)

    def write_signal(self, junction_id: str, state: dict):
        """Call only when the controller's phase actually changes - there's
        no daily write quota to protect anymore, but it's still wasteful to
        write every tick."""
        self._enqueue("signals", junction_id, state)

    def write_live_counts(self, junction_id: str, counts: dict):
        self._enqueue("live_counts", junction_id, counts)

    def write_traffic_log(self, junction_id: str, minute: str, data: dict):
        self._enqueue("traffic_logs", f"{junction_id}_{minute}", data)

    def write_prediction(self, junction_id: str, data: dict):
        self._enqueue("predictions", junction_id, data)

    def write_short_prediction(self, junction_id: str, data: dict):
        self._enqueue("short_predictions", junction_id, data)

    def write_authorised_vehicle(self, vehicle_id: str, data: dict):
        self._enqueue("authorised_vehicles", vehicle_id, data)

    def add_emergency_request(self, data: dict):
        self._enqueue("emergency_requests", None, data)

    def write_emergency_active(self, data: dict):
        self._enqueue("emergency", "active", data)

    def add_emergency_trip(self, data: dict):
        self._enqueue("emergency_trips", None, data)

    def write_accident(self, accident_id: str, data: dict):
        self._enqueue("accidents", accident_id, data)

    def add_alert(self, data: dict):
        self._enqueue("alerts", None, data)

    def add_violation(self, data: dict):
        self._enqueue("violations", None, data)

    def write_air_quality(self, junction_id: str, data: dict):
        self._enqueue("air_quality", junction_id, data)

    def add_air_quality_log(self, data: dict):
        self._enqueue("air_quality_logs", None, data)

    def write_metrics(self, junction_id: str, date: str, data: dict):
        self._enqueue("metrics", f"{junction_id}_{date}", data)

    def write_daily_report(self, date: str, data: dict):
        self._enqueue("daily_reports", date, data)

    def add_command(self, data: dict):
        self._enqueue("commands", None, data)

    def write_command_status(self, command_id: str, data: dict):
        self._enqueue("commands", command_id, data)

    def write_user(self, uid: str, data: dict):
        self._enqueue("users", uid, data)

    def write_system_models(self, data: dict):
        self._enqueue("system", "models", data)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def read_pending(self, collection: str, field: str = "status", value: str = "pending"):
        """Kept for interface compatibility with the old client - every
        caller in this codebase passes field="status" (the only equality
        filter the polling listeners need), backed by the dedicated column."""
        if not self.enabled:
            return []
        assert field == "status", f"read_pending only supports field='status', got {field!r}"
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, data FROM documents WHERE collection=? AND status=?", (collection, value)
            ).fetchall()
        return [{"id": doc_id, **json.loads(data)} for doc_id, data in rows]

    def get_doc(self, collection: str, doc_id: str):
        """Single-document fetch - replaces raw `._db.collection(c).document(id).get()`
        call sites (green_corridor.py, ambulance_sim.py, authorised.py, accidents/manager.py, api/server.py)."""
        if not self.enabled:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM documents WHERE collection=? AND id=?", (collection, doc_id)
            ).fetchone()
        return {"id": doc_id, **json.loads(row[0])} if row else None

    def list_docs(self, collection: str, limit: int = 100, order_by_ts: str = None, status: str = None):
        """Collection listing with an optional status filter and/or ordering
        by the shared `ts` column - covers the frontend's limit()/orderBy()
        needs and replaces raw `._db.collection(c).stream()` call sites
        (road_graph.py, green_corridor.py's junction lookup)."""
        if not self.enabled:
            return []
        sql = "SELECT id, data FROM documents WHERE collection=?"
        params = [collection]
        if status is not None:
            sql += " AND status=?"
            params.append(status)
        if order_by_ts:
            sql += f" ORDER BY ts {'DESC' if order_by_ts == 'desc' else 'ASC'}"
        sql += " LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [{"id": doc_id, **json.loads(data)} for doc_id, data in rows]

    def list_all(self, collection: str):
        """Full-collection fetch, no limit - only for small/bounded
        collections (metrics; daily_report.py's own reasoning already
        assumes this is cheap: junctions x days)."""
        if not self.enabled:
            return []
        with self._lock:
            rows = self._conn.execute("SELECT id, data FROM documents WHERE collection=?", (collection,)).fetchall()
        return [{"id": doc_id, **json.loads(data)} for doc_id, data in rows]

    def query_range(self, collection: str, start_ts: float, end_ts: float):
        """ts-range query ([start_ts, end_ts)), replacing daily_report.py's
        per-collection Firestore FieldFilter range query - no field name
        needed since every collection's business timestamp is normalized
        into the same `ts` column at write time (see _TS_FIELDS)."""
        if not self.enabled:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, data FROM documents WHERE collection=? AND ts>=? AND ts<?",
                (collection, start_ts, end_ts),
            ).fetchall()
        return [{"id": doc_id, **json.loads(data)} for doc_id, data in rows]

    def delete_doc(self, collection: str, doc_id: str):
        if not self.enabled:
            return
        with self._lock:
            self._conn.execute("DELETE FROM documents WHERE collection=? AND id=?", (collection, doc_id))
            self._conn.commit()


_client = None


def get_client() -> SQLiteClient:
    global _client
    if _client is None:
        _client = SQLiteClient()
    return _client
