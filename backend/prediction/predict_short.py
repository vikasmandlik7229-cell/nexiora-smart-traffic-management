"""Phase 7B: live next-5/10-minute predictions from a rolling per-lane
buffer, published to Firestore `short_predictions/{junctionId}`.

Usage as a library (wire into run_signals.py's main loop):
    buffer = RollingBuffer()
    buffer.push("lane1", count=12)   # call once per minute per lane
    predictions = buffer.predict_all()
    publish(predictions)

Run standalone for a demo against the synthetic data:
    python -m prediction.predict_short
"""
import json
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd

import config
from prediction.train_short import FEATURE_COLUMNS, N_LAGS, congestion_level

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
DATA_DIR = HERE / "data"

LANES = ["lane1", "lane2", "lane3", "lane4"]
BUFFER_LEN = N_LAGS + 1  # need current + N_LAGS history for rolling features


class RollingBuffer:
    def __init__(self):
        bundle = joblib.load(MODELS_DIR / "short_model.joblib")
        self.models = bundle["models"]  # {5: model, 10: model}
        self.encoder = bundle["encoder"]
        self._history = {lane: deque(maxlen=BUFFER_LEN) for lane in LANES}
        self._last_alert_at = {lane: None for lane in LANES}

    def push(self, lane: str, count: float, when: datetime = None) -> None:
        when = when or datetime.now()
        self._history[lane].append((when, count))

    def _features_for(self, lane: str):
        hist = list(self._history[lane])
        if len(hist) < BUFFER_LEN:
            return None  # not enough history yet
        counts = [c for _, c in hist]
        now_ts, _ = hist[-1]
        lags = counts[-2::-1][:N_LAGS]  # most recent N_LAGS values before "now"
        rolling_mean_5 = float(np.mean(counts[-6:-1]))
        rolling_mean_10 = float(np.mean(counts[-11:-1])) if len(counts) >= 11 else rolling_mean_5
        trend = rolling_mean_5 - rolling_mean_10
        hour_frac = now_ts.hour + now_ts.minute / 60
        hour_sin = np.sin(2 * np.pi * hour_frac / 24)
        hour_cos = np.cos(2 * np.pi * hour_frac / 24)
        day_of_week = now_ts.weekday()
        is_weekend = int(day_of_week >= 5)

        numeric = lags + [rolling_mean_5, rolling_mean_10, trend, hour_sin, hour_cos, day_of_week, is_weekend]
        lane_onehot = self.encoder.transform(pd.DataFrame({"laneId": [lane]}))[0]
        return np.array(numeric + list(lane_onehot)).reshape(1, -1)

    def predict_all(self) -> dict:
        now = datetime.now().isoformat()
        predictions = {}
        for lane in LANES:
            feats = self._features_for(lane)
            if feats is None:
                predictions[lane] = {"status": "warming up, need more history"}
                continue
            current = self._history[lane][-1][1]
            in5 = float(self.models[5].predict(feats)[0])
            in10 = float(self.models[10].predict(feats)[0])
            predictions[lane] = {
                "now": current,
                "in5": in5,
                "in10": in10,
                "level": congestion_level(in5),
            }
        return {"generatedAt": now, "lanes": predictions}

    def check_alerts(self, client, junction_id: str, predictions: dict) -> None:
        """Fires a 'prediction' alert for any lane predicted 'high' in the
        next 5 minutes, at most once per PREDICTION_ALERT_COOLDOWN_S per lane
        (CLAUDE.md 6.7) - _last_alert_at exists precisely to make this
        cooldown per-lane rather than a single shared throttle."""
        if not client.enabled:
            return
        now = time.time()
        for lane, pred in predictions.get("lanes", {}).items():
            if pred.get("level") != "high":
                continue
            last = self._last_alert_at.get(lane)
            if last is not None and now - last < config.PREDICTION_ALERT_COOLDOWN_S:
                continue
            client.add_alert({
                "type": "prediction", "severity": "medium", "public": True,
                "message": f"{lane} at {junction_id} predicted to reach high congestion within 5 minutes "
                            f"(~{pred.get('in5', 0):.0f} vehicles).",
                "junctionId": junction_id, "timestamp": now, "read": False,
            })
            self._last_alert_at[lane] = now


def publish(predictions: dict, junction_id: str = "J1"):
    out_path = DATA_DIR / "latest_short_predictions.json"
    out_path.write_text(json.dumps(predictions, indent=2))

    from db.sql_client import get_client
    client = get_client()
    if client.enabled:
        client.write_short_prediction(junction_id, predictions)
        print(f"published short-term predictions for {junction_id} to the database (and {out_path})")
    else:
        print(f"Database offline - wrote short-term predictions to {out_path} only")


def demo_from_synthetic_data():
    """Standalone demo: replays the tail of minute_traffic.csv through the
    buffer so you can see predict_short.py work without a live pipeline."""
    df = pd.read_csv(DATA_DIR / "minute_traffic.csv")
    buffer = RollingBuffer()
    for lane in LANES:
        tail = df[df["laneId"] == lane].tail(BUFFER_LEN)
        for _, row in tail.iterrows():
            buffer.push(lane, row["count"], when=pd.to_datetime(row["timestamp"]))

    predictions = buffer.predict_all()
    publish(predictions)
    from db.sql_client import get_client
    buffer.check_alerts(get_client(), "J1", predictions)
    for lane, p in predictions["lanes"].items():
        print(f"  {lane}: now={p.get('now')}, in5={p.get('in5', 0):.1f}, "
              f"in10={p.get('in10', 0):.1f}, level={p.get('level')}")
    time.sleep(2)  # let the Firestore write queue flush before this one-shot script exits


if __name__ == "__main__":
    demo_from_synthetic_data()
