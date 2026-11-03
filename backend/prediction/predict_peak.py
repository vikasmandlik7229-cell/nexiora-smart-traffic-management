"""Phase 7A: predict the next 24 hours of traffic per junction and flag the
top 20% as peak hours, published to Firestore `predictions/{junctionId}`.
Still writes a local JSON copy too, and degrades to local-only if Firebase
is offline.

Run from backend/, with the venv active, after train_peak.py:
    python -m prediction.predict_peak             # predict once
    python -m prediction.predict_peak --every 60   # loop every 60s
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd

import config
from prediction.train_peak import FEATURE_COLUMNS, add_cyclical_hour, build_features

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
DATA_DIR = HERE / "data"


def predict_next_24h(model, encoder) -> dict:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    predictions = {}

    for junction in config.JUNCTIONS:
        jid = junction["id"]
        hours = [now + timedelta(hours=i) for i in range(24)]
        df = pd.DataFrame({
            "junctionId": jid,
            "hour": [h.hour for h in hours],
            "dayOfWeek": [h.weekday() for h in hours],
            "isWeekend": [int(h.weekday() >= 5) for h in hours],
        })
        df = add_cyclical_hour(df)
        X, _ = build_features(df, encoder=encoder)
        predicted_counts = model.predict(X)

        threshold = np.percentile(predicted_counts, 80)  # top 20%
        hourly = [
            {"timestamp": h.isoformat(), "predictedCount": float(c), "isPeak": bool(c >= threshold)}
            for h, c in zip(hours, predicted_counts)
        ]
        peak_hours = [row["timestamp"] for row in hourly if row["isPeak"]]

        predictions[jid] = {"hourly": hourly, "peakHours": peak_hours, "generatedAt": now.isoformat()}

    return predictions


def publish(predictions: dict):
    out_path = DATA_DIR / "latest_peak_predictions.json"
    out_path.write_text(json.dumps(predictions, indent=2))

    from db.sql_client import get_client
    client = get_client()
    if client.enabled:
        for jid, data in predictions.items():
            client.write_prediction(jid, data)
        print(f"[{datetime.now().isoformat()}] published predictions for {len(predictions)} junctions to the database "
              f"(and wrote a local copy to {out_path})")
    else:
        print(f"[{datetime.now().isoformat()}] Firebase offline - wrote predictions for {len(predictions)} "
              f"junctions to {out_path} only")


def start_background(interval_s: int = 3600):
    """Loads the model synchronously (so a missing model raises here, in the
    caller's thread, not silently inside a background thread) then runs the
    hourly prediction loop in the background."""
    import threading
    bundle = joblib.load(MODELS_DIR / "peak_model.joblib")  # fail fast if untrained
    model, encoder = bundle["model"], bundle["encoder"]
    stop_event = threading.Event()

    def _loop():
        while not stop_event.is_set():
            predictions = predict_next_24h(model, encoder)
            publish(predictions)
            stop_event.wait(interval_s)

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--every", type=int, default=0, help="seconds between predictions; 0 = run once")
    args = parser.parse_args()

    bundle = joblib.load(MODELS_DIR / "peak_model.joblib")
    model, encoder = bundle["model"], bundle["encoder"]

    while True:
        predictions = predict_next_24h(model, encoder)
        publish(predictions)
        for jid, p in predictions.items():
            print(f"  {jid}: {len(p['peakHours'])} peak hours in the next 24h")
        if args.every <= 0:
            time.sleep(2)  # let the Firestore write queue flush before this one-shot run exits
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
