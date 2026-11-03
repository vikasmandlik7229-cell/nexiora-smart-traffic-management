"""One-time seed data for a fresh local SQLite database: junctions, roads,
3 authorised vehicles, an inactive emergency/active doc, system/models, and
(new - simpler than the old Firebase Auth console step) the two demo user
accounts directly, with locally hashed passwords.

Run from backend/, with the venv active:
    python -m db.seed
    python -m db.seed --set-role someone@example.com controller somepassword
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from db.auth import hash_password
from db.sql_client import get_client

# Same credentials already documented in README.md / docs/DEMO_SCRIPT.md -
# kept identical so existing docs don't need to change.
DEMO_USERS = [
    {"email": "controller@nexiora.demo", "password": "Nexiora#Ctrl2026", "role": "controller"},
    {"email": "driver@nexiora.demo", "password": "Nexiora#Drive2026", "role": "driver", "vehicleId": "AMB001"},
]


def seed_junctions(client):
    for j in config.JUNCTIONS:
        client.write_junction(j["id"], {
            "name": j["name"],
            "lat": j["lat"],
            "lng": j["lng"],
            "isVirtual": j["id"] != "J1",
            "approaches": {"lane1": 0, "lane2": 90, "lane3": 180, "lane4": 270} if j["id"] == "J1" else {},
        })
    print(f"Seeded {len(config.JUNCTIONS)} junctions.")


def seed_roads(client):
    # Simple chain J1-J2-J3-J4, both directions, matching the placeholder
    # JUNCTIONS layout until real coordinates replace it (CLAUDE.md 4.5).
    ids = [j["id"] for j in config.JUNCTIONS]
    count = 0
    for a, b in zip(ids, ids[1:]):
        for from_id, to_id in ((a, b), (b, a)):
            client.write_road(f"{from_id}_{to_id}", {
                "from": from_id, "to": to_id,
                "distanceM": 1000, "baseTimeKmph": 40,
                "status": "open", "congestionFactor": 1.0,
            })
            count += 1
    print(f"Seeded {count} road segments.")


def seed_authorised_vehicles(client):
    # baseJunction = where this vehicle is normally stationed/idle (its
    # depot) - used by accidents/manager.py to work out which authorised
    # vehicle is nearest an accident and notify that one specifically.
    # Spread across the 4-junction grid so "nearest" is actually meaningful.
    vehicles = [
        {"id": "AMB001", "type": "ambulance", "tagId": "RFID-AMB-001", "hospital": "City General Hospital", "driverName": "Ramesh Kumar", "active": True, "baseJunction": "J1"},
        {"id": "AMB002", "type": "ambulance", "tagId": "RFID-AMB-002", "hospital": "St. Mary's Hospital", "driverName": "Suresh Patel", "active": True, "baseJunction": "J3"},
        {"id": "FIRE001", "type": "fire", "tagId": "RFID-FIRE-001", "hospital": None, "driverName": "Fire Station 1", "active": True, "baseJunction": "J4"},
    ]
    for v in vehicles:
        vehicle_id = v.pop("id")
        client.write_authorised_vehicle(vehicle_id, v)
    print(f"Seeded {len(vehicles)} authorised vehicles.")


def seed_emergency_and_models(client):
    client.write_emergency_active({
        "active": False, "vehicleId": None, "lat": None, "lng": None,
        "speedKmph": 0, "routeJunctions": [], "routePolyline": [],
        "nextJunctionId": None, "etaNextS": None, "preempted": [], "startedAt": None,
    })
    client.write_system_models({
        "detectorName": config.YOLO_MODEL_NAME,
        "classes": ["car", "bike", "auto", "bus", "truck"],
        # Ultralytics' own validator output for the final epoch (the "all"
        # row), training/runs/train_v8n_5cls.log line 78748 and the last row
        # of training/runs/uvh26_v8n_5cls/results.csv - a real measured
        # number, not invented (CLAUDE.md section 10).
        "mAP50": 0.901,
        "mAP50_95": 0.750,
        "emergencyClassifier": None,  # T4 blocked pending dataset, see CLAUDE.md 4.2
    })
    print("Seeded emergency/active (inactive) and system/models.")


def create_user(client, email: str, password: str, role: str, **extra):
    """Creates (or resets) a local login - no more "create the user in the
    Firebase Auth console first" manual step, since there's no cloud auth
    provider anymore."""
    hashed = hash_password(password)
    client.write_user(email, {"email": email, "role": role, **hashed, **extra})
    print(f"User {email} set to role '{role}'.")


def seed_demo_users(client):
    for u in DEMO_USERS:
        u = dict(u)
        create_user(client, u.pop("email"), u.pop("password"), u.pop("role"), **u)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-role", nargs=3, metavar=("EMAIL", "ROLE", "PASSWORD"))
    args = parser.parse_args()

    client = get_client()
    if not client.enabled:
        print("Database is not connected - check config.SQLITE_DB_PATH. Nothing seeded.")
        return

    if args.set_role:
        email, role, password = args.set_role
        create_user(client, email, password, role)
        time.sleep(0.2)
        return

    seed_junctions(client)
    seed_roads(client)
    seed_authorised_vehicles(client)
    seed_emergency_and_models(client)
    seed_demo_users(client)
    time.sleep(0.5)  # let the background writer flush before the script exits
    print("Seed complete.")


if __name__ == "__main__":
    main()
