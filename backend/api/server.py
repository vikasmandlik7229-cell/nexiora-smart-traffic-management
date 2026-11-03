"""Phase 4/6.11: local FastAPI server - health check, MJPEG live stream of
the annotated J1 video, evidence images (violations/accidents), report
downloads, local login, and the generic JSON data API that replaced
Firestore's real-time listeners (the website now polls these endpoints -
see web/src/hooks/useDoc.js and useCollection.js). Protected endpoints
require a locally-issued JWT (db/auth.py) with role 'controller' (or
'driver' where noted); the stream is public only while config.PUBLIC_STREAM
is True.

Runs inside main.py in a background thread; the detection loop pushes
frames into `frame_buffer` for this module to serve. Can also be run
standalone for testing:
    uvicorn api.server:app --port 8000
"""
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import config
from db.auth import hash_password, issue_token, verify_password, verify_token
from db.sql_client import get_client

app = FastAPI(title="Smart Traffic AI Local API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
)


class FrameBuffer:
    """Thread-safe single-slot-per-key buffer for the latest annotated
    frame(s). The detection loop calls update(); the stream endpoint reads
    via get()."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frames = {}

    def update(self, key: str, frame) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self._lock:
                self._frames[key] = buf.tobytes()

    def get(self, key: str):
        with self._lock:
            return self._frames.get(key)


frame_buffer = FrameBuffer()
_module_health = {}


def set_module_health(name: str, ok: bool) -> None:
    _module_health[name] = ok


@app.get("/api/health")
def health():
    return {"status": "ok", "modules": _module_health}


def _decode_token(authorization: str = None, token: str = None) -> Optional[dict]:
    """Returns the decoded JWT payload ({"sub": email, "role": ...}), or
    None if there's no token or it's invalid/expired - callers decide
    whether that's a hard failure (protected endpoint) or just means
    "treat as a logged-out/public request" (generic read endpoints)."""
    raw = None
    if authorization and authorization.startswith("Bearer "):
        raw = authorization.split(" ", 1)[1]
    elif token:
        raw = token
    if not raw:
        return None
    try:
        return verify_token(raw)
    except Exception:
        return None


def _require_role(authorization: str, token: str, *roles: str) -> dict:
    decoded = _decode_token(authorization, token)
    if not decoded:
        raise HTTPException(401, "missing or invalid auth token")
    if decoded.get("role") not in roles:
        raise HTTPException(403, f"one of roles {roles} required")
    return decoded


def _verify_controller_token(authorization: str = None, token: str = None) -> None:
    _require_role(authorization, token, "controller")


def _mjpeg_generator(key: str):
    while True:
        frame = frame_buffer.get(key)
        if frame is not None:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(1 / 15)


@app.get("/api/stream/j1")
def stream_j1(lane: str = Query(default=None), authorization: str = Header(default=None), token: str = Query(default=None)):
    if not config.PUBLIC_STREAM:
        _verify_controller_token(authorization, token)
    key = lane if lane else "grid"
    return StreamingResponse(_mjpeg_generator(key), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/evidence/violations/{filename}")
def evidence_violation(filename: str, authorization: str = Header(default=None), token: str = Query(default=None)):
    _verify_controller_token(authorization, token)
    path = config.DATA_DIR / "violations_images" / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@app.get("/api/evidence/accidents/{filename}")
def evidence_accident(filename: str, authorization: str = Header(default=None), token: str = Query(default=None)):
    _verify_controller_token(authorization, token)
    path = config.DATA_DIR / "accident_images" / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@app.get("/api/reports")
def list_reports(authorization: str = Header(default=None), token: str = Query(default=None)):
    _verify_controller_token(authorization, token)
    reports_dir = config.BASE_DIR / "reports" / "output"
    if not reports_dir.exists():
        return {"reports": []}
    return {"reports": sorted(p.name for p in reports_dir.iterdir() if p.is_file())}


@app.get("/api/reports/{filename}")
def get_report(filename: str, authorization: str = Header(default=None), token: str = Query(default=None)):
    _verify_controller_token(authorization, token)
    path = config.BASE_DIR / "reports" / "output" / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


# ------------------------------------------------------------------
# Local login (replaces Firebase Authentication)
# ------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest):
    user = get_client().get_doc("users", body.email)
    if not user or not verify_password(body.password, user.get("salt", ""), user.get("passwordHash", "")):
        raise HTTPException(401, "invalid email or password")
    token = issue_token(user["email"], user["role"], vehicle_id=user.get("vehicleId"))
    return {"token": token, "email": user["email"], "role": user["role"], "vehicleId": user.get("vehicleId")}


@app.get("/api/auth/me")
def me(authorization: str = Header(default=None), token: str = Query(default=None)):
    decoded = _decode_token(authorization, token)
    if not decoded:
        raise HTTPException(401, "invalid or missing token")
    return {"email": decoded["sub"], "role": decoded["role"], "vehicleId": decoded.get("vehicleId")}


# ------------------------------------------------------------------
# Generic JSON data API (replaces Firestore's onSnapshot real-time reads -
# the website polls these every couple of seconds; see web/src/hooks).
# Permissions here are a direct, auditable port of the old
# backend/firebase/firestore.rules table.
# ------------------------------------------------------------------
_CONTROLLER_ONLY_COLLECTIONS = {
    "violations", "emergency_trips", "daily_reports", "traffic_logs",
    "commands", "accident_reports", "authorised_vehicles",
}
_PUBLIC_COLLECTIONS = {
    "junctions", "roads", "signals", "live_counts", "predictions", "short_predictions",
    "air_quality", "air_quality_logs", "metrics", "accidents", "emergency", "system",
}
# "alerts", "emergency_requests" and "users" have per-document rules instead
# of a flat collection-level one - handled inline below.
_KNOWN_COLLECTIONS = _CONTROLLER_ONLY_COLLECTIONS | _PUBLIC_COLLECTIONS | {"alerts", "emergency_requests", "users"}


@app.get("/api/collection/{name}")
def get_collection(
    name: str,
    limit: int = 100,
    order_by: str = Query(default=None),
    dir: str = Query(default="desc"),
    status: str = Query(default=None),
    authorization: str = Header(default=None),
    token: str = Query(default=None),
):
    if name not in _KNOWN_COLLECTIONS:
        raise HTTPException(404, f"unknown collection: {name}")

    decoded = _decode_token(authorization, token)
    role = decoded.get("role") if decoded else None
    email = decoded.get("sub") if decoded else None
    vehicle_id = decoded.get("vehicleId") if decoded else None

    if name in _CONTROLLER_ONLY_COLLECTIONS and role != "controller":
        raise HTTPException(403, "controller role required")
    if name == "users" and role != "controller":
        raise HTTPException(403, "controller role required")

    order_by_ts = dir if order_by == "timestamp" else None
    docs = get_client().list_docs(name, limit=limit, order_by_ts=order_by_ts, status=status)

    if name == "alerts":
        # Public alerts, or a controller (sees everything), or a private
        # "dispatch" alert targeted at the vehicle this driver is logged in
        # as (accidents/manager.py's nearest-ambulance notification).
        docs = [d for d in docs if d.get("public") or role == "controller"
                or (vehicle_id and d.get("vehicleId") == vehicle_id)]
    elif name == "emergency_requests" and role != "controller":
        if not email:
            raise HTTPException(401, "login required")
        docs = [d for d in docs if d.get("requestedBy") == email]

    return {"docs": docs}


@app.get("/api/doc/{name}/{doc_id}")
def get_doc_endpoint(
    name: str,
    doc_id: str,
    authorization: str = Header(default=None),
    token: str = Query(default=None),
):
    if name not in _KNOWN_COLLECTIONS:
        raise HTTPException(404, f"unknown collection: {name}")
    decoded = _decode_token(authorization, token)
    role = decoded.get("role") if decoded else None
    if name in _CONTROLLER_ONLY_COLLECTIONS and role != "controller":
        raise HTTPException(403, "controller role required")
    doc = get_client().get_doc(name, doc_id)
    if doc is None:
        raise HTTPException(404, "not found")
    return doc


# ------------------------------------------------------------------
# Named write endpoints - one per website write action that used to be a
# direct Firestore write (web/src/lib/commands.js, accidents.js,
# emergency.js, vehicles.js). Permissions again mirror firestore.rules.
# ------------------------------------------------------------------
class CommandBody(BaseModel):
    junctionId: str
    type: str
    laneId: Optional[str] = None
    durationS: Optional[float] = None


@app.post("/api/commands")
def create_command(body: CommandBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    decoded = _require_role(authorization, token, "controller")
    data = {"junctionId": body.junctionId, "type": body.type, "status": "pending",
            "reason": "", "requestedBy": decoded["sub"]}
    if body.laneId is not None:
        data["laneId"] = body.laneId
    if body.durationS is not None:
        data["durationS"] = body.durationS
    return {"id": get_client().create_doc("commands", data)}


class AccidentReportBody(BaseModel):
    junctionId: Optional[str] = None
    roadId: Optional[str] = None
    laneId: Optional[str] = None
    severity: str
    arrivalRatePcuPerMin: float = 6.0


@app.post("/api/accident-reports")
def report_accident(body: AccidentReportBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    decoded = _require_role(authorization, token, "controller")
    data = body.model_dump()
    data.update({"requestedBy": decoded["sub"], "status": "pending"})
    return {"id": get_client().create_doc("accident_reports", data)}


@app.patch("/api/accidents/{accident_id}/resolve")
def resolve_accident_endpoint(accident_id: str, authorization: str = Header(default=None), token: str = Query(default=None)):
    _require_role(authorization, token, "controller")
    get_client()._enqueue("accidents", accident_id, {"status": "resolving"})
    return {"ok": True}


class MarkAlertsReadBody(BaseModel):
    ids: List[str]


@app.post("/api/alerts/mark-read")
def mark_alerts_read(body: MarkAlertsReadBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    """Called when the dashboard's notification bell is opened (see
    DashboardLayout.jsx) - marks whichever alerts are currently visible as
    read, so the unread badge count actually clears instead of climbing
    forever (nothing else in this app ever set `read`)."""
    _require_role(authorization, token, "controller")
    client = get_client()
    for alert_id in body.ids:
        client._enqueue("alerts", alert_id, {"read": True})
    return {"ok": True, "count": len(body.ids)}


class EmergencyRequestBody(BaseModel):
    vehicleId: str
    tagId: str
    destinationJunction: str
    source: str = "web"


@app.post("/api/emergency-requests")
def create_emergency_request(body: EmergencyRequestBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    decoded = _require_role(authorization, token, "driver", "controller")
    data = body.model_dump()
    data.update({"requestedBy": decoded["sub"], "status": "pending", "reason": ""})
    return {"id": get_client().create_doc("emergency_requests", data)}


class TripControlBody(BaseModel):
    endRequested: bool = True


@app.put("/api/trip-control/{vehicle_id}")
def set_trip_control(vehicle_id: str, body: TripControlBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    _require_role(authorization, token, "driver", "controller")
    get_client()._enqueue("trip_control", vehicle_id, {"endRequested": body.endRequested})
    return {"ok": True}


class AuthorisedVehicleBody(BaseModel):
    type: Optional[str] = None
    tagId: Optional[str] = None
    hospital: Optional[str] = None
    driverName: Optional[str] = None
    active: Optional[bool] = None


@app.put("/api/authorised-vehicles/{vehicle_id}")
def upsert_authorised_vehicle(vehicle_id: str, body: AuthorisedVehicleBody, authorization: str = Header(default=None), token: str = Query(default=None)):
    _require_role(authorization, token, "controller")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    get_client().write_authorised_vehicle(vehicle_id, data)
    return {"ok": True}


def run_server():
    import uvicorn
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="warning")


def start_background():
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
