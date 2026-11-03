"""Phase 7B: synthetic per-minute traffic data for short-term (5/10 min)
prediction, with realistic congestion build-ups (not just independent
per-minute noise) so lag/rolling features actually carry signal.

Run from backend/, with the venv active:
    python -m prediction.generate_minute_data
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from prediction.generate_hourly_data import diurnal_base

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DAYS = 14
LANES = ["lane1", "lane2", "lane3", "lane4"]
RNG = np.random.default_rng(seed=1)


def congestion_wave(n_minutes: int) -> np.ndarray:
    """Mean-reverting random walk (Ornstein-Uhlenbeck-ish): creates slow
    build-ups and decays instead of independent per-minute noise, so a
    jam forming/clearing actually looks like a jam forming/clearing."""
    wave = np.zeros(n_minutes)
    theta, sigma = 0.02, 1.2  # reversion speed, step size
    for i in range(1, n_minutes):
        wave[i] = wave[i - 1] - theta * wave[i - 1] + RNG.normal(0, sigma)
    return wave


def generate_lane(start: datetime, n_minutes: int) -> pd.DataFrame:
    minutes = [start + timedelta(minutes=i) for i in range(n_minutes)]
    hours = np.array([m.hour + m.minute / 60 for m in minutes])
    base = diurnal_base(hours) * 0.6  # scaled down from hourly totals to per-minute rate
    wave = congestion_wave(n_minutes)
    noise = RNG.normal(0, 1.0, n_minutes)
    count = np.clip(np.round(base + wave + noise), 0, None)

    return pd.DataFrame({
        "timestamp": [m.isoformat() for m in minutes],
        "minute": [m.minute for m in minutes],
        "hour": [m.hour for m in minutes],
        "dayOfWeek": [m.weekday() for m in minutes],
        "isWeekend": [int(m.weekday() >= 5) for m in minutes],
        "count": count,
    })


def main():
    DATA_DIR.mkdir(exist_ok=True)
    n_minutes = DAYS * 24 * 60
    start = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=n_minutes)

    frames = []
    for lane in LANES:
        df = generate_lane(start, n_minutes)
        df["laneId"] = lane
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)
    out_csv = DATA_DIR / "minute_traffic.csv"
    full.to_csv(out_csv, index=False)
    print(f"Wrote {len(full)} rows ({DAYS} days x 1440 min x {len(LANES)} lanes) to {out_csv}")


if __name__ == "__main__":
    main()
