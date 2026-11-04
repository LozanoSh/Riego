from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .synthetic_data import build_channel_training_data, build_sector_training_data


@dataclass
class ModelBundle:
    channel_loss: RandomForestRegressor
    sector_with_sensor: RandomForestRegressor
    sector_proxy: RandomForestRegressor
    metrics: dict


def _fit_rf(X: pd.DataFrame, y: np.ndarray, random_state: int):
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestRegressor(
        n_estimators=160,
        max_depth=11,
        min_samples_leaf=3,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    return model, {
        "mae": float(mean_absolute_error(yte, pred)),
        "r2": float(r2_score(yte, pred)),
        "n_total": len(X),
        "n_train": len(Xtr),
        "n_test": len(Xte),
    }


def build_models() -> ModelBundle:
    Xc, yc = build_channel_training_data()
    channel, mc = _fit_rf(Xc, yc, 42)

    Xs, ys = build_sector_training_data(with_sensor=True)
    sector_sensor, ms = _fit_rf(Xs, ys, 7)

    Xp, yp = build_sector_training_data(with_sensor=False)
    sector_proxy, mp = _fit_rf(Xp, yp, 11)

    return ModelBundle(
        channel_loss=channel,
        sector_with_sensor=sector_sensor,
        sector_proxy=sector_proxy,
        metrics={"canal": mc, "sector_sensor": ms, "sector_proxy": mp},
    )
