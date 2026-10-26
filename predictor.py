"""Standalone runtime predictor for the saved next-month total model."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd  # Kept as an explicit runtime dependency promised by the project.

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


def _feature_row(history: list[float], next_month: int, features: list[str]) -> tuple[dict[str, float], float]:
    h = np.asarray(history, dtype=float)
    n = len(h)
    def lag(k: int) -> float:
        return float(h[-k]) if n >= k else np.nan
    mean3 = float(h[-3:].mean())
    values = {
        "lag_1": lag(1), "lag_2": lag(2), "lag_3": lag(3), "lag_6": lag(6), "lag_12": lag(12),
        "roll_mean_3": mean3, "roll_mean_6": float(h[-6:].mean()) if n >= 6 else np.nan,
        "roll_std_3": float(h[-3:].std(ddof=0)),
        "trend": mean3 - float(h[-6:-3].mean()) if n >= 6 else np.nan,
        "n_months_history": float(n), "month_sin": float(np.sin(2 * np.pi * next_month / 12)),
        "month_cos": float(np.cos(2 * np.pi * next_month / 12)),
        "is_december": float(next_month == 12), "is_january": float(next_month == 1),
    }
    for name in ("lag_1", "lag_2", "lag_3", "lag_6", "lag_12", "roll_mean_3", "roll_mean_6", "roll_std_3", "trend"):
        values[name] /= mean3
    return {name: values[name] for name in features}, mean3


def _tier(n: int) -> str:
    return "3-5" if n <= 5 else "6-11" if n <= 11 else "12+"


def predict_next_month(monthly_totals: list[float], next_month: int) -> float:
    """Predict a completed-history user's total expense in calendar ``next_month``.

    The history must be oldest to newest and must exclude any in-progress month.
    """
    if not 1 <= next_month <= 12:
        raise ValueError("next_month must be an integer from 1 through 12")
    history = [float(x) for x in monthly_totals]
    if any(not np.isfinite(x) or x < 0 for x in history):
        raise ValueError("monthly_totals must contain finite, non-negative values")
    if not history:
        return 0.0
    if len(history) < 3:
        return float(np.mean(history))
    moving_average = float(np.mean(history[-3:]))
    meta = json.loads((ARTIFACT_DIR / "model_meta.json").read_text(encoding="utf-8"))
    if moving_average == 0 or meta["chosen_method_per_tier"][_tier(len(history))] != "ml":
        return moving_average
    features, scale = _feature_row(history, next_month, meta["feature_list"])
    model = joblib.load(ARTIFACT_DIR / "model.joblib")
    prediction = float(model.predict(pd.DataFrame([features], columns=meta["feature_list"]))[0] * scale)
    return max(0.0, prediction)
