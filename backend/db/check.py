"""Quick sanity check: reads back the collections seed.py writes and prints
a summary, so you can confirm the local database actually has data without
opening a SQLite browser.

Run from backend/, with the venv active:
    python -m db.check
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.sql_client import get_client

COLLECTIONS_TO_CHECK = [
    "junctions", "roads", "authorised_vehicles", "emergency", "system", "users",
]


def main():
    client = get_client()
    if not client.enabled:
        print("Database is not connected - nothing to check.")
        return

    for name in COLLECTIONS_TO_CHECK:
        docs = client.list_docs(name, limit=1000)
        print(f"{name}: {len(docs)} document(s)")
        for d in docs[:5]:
            shown = dict(d)
            if "passwordHash" in shown:
                shown["passwordHash"] = "***"
            print(f"  - {d['id']}: {shown}")


if __name__ == "__main__":
    main()
