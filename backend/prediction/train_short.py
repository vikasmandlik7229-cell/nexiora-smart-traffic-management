"""Phase 7B: train next-5/10-minute traffic predictors per lane.

Features: lag_1..lag_10, rolling means, short-term trend, hour_sin/cos,
dayOfWeek, isWeekend, laneId. Compares a naive baseline (persistence)
against Linear Regression and Random Forest, using a TIME-BASED split
(not random) since shuffling would leak future minutes into training.

Run from backend/, with the venv active, after generate_minute_data.py:
    python -m prediction.train_short
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import OneHotEncoder

import config

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
MODELS_DIR = HERE / "models"
CHARTS_DIR = HERE / "charts"

N_LAGS = 10
HORIZONS = (5, 10)
FEATURE_COLUMNS = [f"lag_{i}" for i in range(1, N_LAGS + 1)] + [
    "rolling_mean_5", "rolling_mean_10", "trend", "hour_sin", "hour_cos", "dayOfWeek", "isWeekend",
]


def congestion_level(pcu: float) -> str:
    capacity = config.LANE_CAPACITY_PCU
    if pcu < 0.4 * capacity:
        return "low"
    if pcu < 0.75 * capacity:
        return "medium"
    return "high"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["laneId", "timestamp"]).reset_index(drop=True)
    out_frames = []
    for lane, g in df.groupby("laneId"):
        g = g.copy()
        for i in range(1, N_LAGS + 1):
            g[f"lag_{i}"] = g["count"].shift(i)
        g["rolling_mean_5"] = g["count"].shift(1).rolling(5).mean()
        g["rolling_mean_10"] = g["count"].shift(1).rolling(10).mean()
        g["trend"] = g["rolling_mean_5"] - g["rolling_mean_10"]
        g["hour_sin"] = np.sin(2 * np.pi * (g["hour"] + g["minute"] / 60) / 24)
        g["hour_cos"] = np.cos(2 * np.pi * (g["hour"] + g["minute"] / 60) / 24)
        for h in HORIZONS:
            g[f"target_{h}"] = g["count"].shift(-h)
        out_frames.append(g)
    return pd.concat(out_frames, ignore_index=True).dropna()


def time_based_split(df: pd.DataFrame, test_fraction=0.2):
    cutoff = df["timestamp"].quantile(1 - test_fraction)
    train = df[df["timestamp"] <= cutoff]
    test = df[df["timestamp"] > cutoff]
    return train, test


def main():
    MODELS_DIR.mkdir(exist_ok=True)
    CHARTS_DIR.mkdir(exist_ok=True)

    raw = pd.read_csv(DATA_DIR / "minute_traffic.csv")
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    df = build_features(raw)

    train_df, test_df = time_based_split(df)
    print(f"Train rows: {len(train_df)}, test rows: {len(test_df)} (time-based split, no shuffling)")

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    lane_train = encoder.fit_transform(train_df[["laneId"]])
    lane_test = encoder.transform(test_df[["laneId"]])

    X_train = np.hstack([train_df[FEATURE_COLUMNS].to_numpy(), lane_train])
    X_test = np.hstack([test_df[FEATURE_COLUMNS].to_numpy(), lane_test])

    results = {}
    best_models = {}
    for h in HORIZONS:
        y_train = train_df[f"target_{h}"].to_numpy()
        y_test = test_df[f"target_{h}"].to_numpy()

        naive_pred = test_df["lag_1"].to_numpy()  # persistence: "still what it was last minute"
        naive_mae = mean_absolute_error(y_test, naive_pred)

        lr = LinearRegression().fit(X_train, y_train)
        lr_pred = lr.predict(X_test)
        lr_mae = mean_absolute_error(y_test, lr_pred)

        rf = RandomForestRegressor(n_estimators=200, max_depth=12, random_state=0).fit(X_train, y_train)
        rf_pred = rf.predict(X_test)
        rf_mae = mean_absolute_error(y_test, rf_pred)

        print(f"\nHorizon t+{h} min:")
        print(f"  naive              MAE={naive_mae:.2f}")
        print(f"  linear_regression  MAE={lr_mae:.2f}")
        print(f"  random_forest      MAE={rf_mae:.2f}")

        results[f"t+{h}"] = {"naive_mae": naive_mae, "linear_regression_mae": lr_mae, "random_forest_mae": rf_mae}
        best_name, best_model, best_pred = min(
            [("linear_regression", lr, lr_pred), ("random_forest", rf, rf_pred)], key=lambda t: mean_absolute_error(y_test, t[2])
        )
        best_models[h] = best_model
        results[f"t+{h}"]["bestModel"] = best_name

        true_level = [congestion_level(v) for v in y_test]
        pred_level = [congestion_level(v) for v in best_pred]
        accuracy = float(np.mean([a == b for a, b in zip(true_level, pred_level)]))
        results[f"t+{h}"]["levelAccuracy"] = accuracy
        print(f"  low/medium/high accuracy ({best_name}): {accuracy:.2%}")

        fig, ax = plt.subplots(figsize=(10, 4))
        sample = slice(0, 300)
        ax.plot(y_test[sample], label="actual", linewidth=1)
        ax.plot(best_pred[sample], label=f"predicted ({best_name})", linewidth=1)
        ax.set_title(f"t+{h} min prediction vs actual (first 300 test minutes)")
        ax.set_ylabel("vehicle count")
        ax.legend()
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / f"short_t{h}_actual_vs_predicted.png")

    joblib.dump({"models": best_models, "encoder": encoder, "feature_columns": FEATURE_COLUMNS},
                MODELS_DIR / "short_model.joblib")
    (MODELS_DIR / "short_metrics.json").write_text(json.dumps(results, indent=2))
    print(f"\nSaved {MODELS_DIR / 'short_model.joblib'}, short_metrics.json, and charts to {CHARTS_DIR}")


if __name__ == "__main__":
    main()
