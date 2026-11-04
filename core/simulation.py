"""Orquesta el turno. No depende de Gradio ni opera compuertas."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .agents import ChannelAuditAgent, DataAgent, DiagnosticAgent, PriorityAgent, normalize_channels, normalize_sectors
from .sensors import simulate_sensors
from .synthetic_data import new_sector

# Unidades internas conservadas: duración del turno en minutos; lluvia en mm/día.
INPUT_LIMITS = [(0, 42), (10, 90), (0, 70), (0, 40), (1, 12), (5, 120), (60, 1440), (0, 48)]


def simulate_turn(models, temp, rh, wind, rain, et0, flow, turn_minutes, sectors_raw, channels_raw, hours=12):
    try:
        values = [float(v) for v in [temp, rh, wind, rain, et0, flow, turn_minutes, hours]]
    except (TypeError, ValueError) as exc:
        raise ValueError("Completá clima, caudal, duración y horizonte con números válidos.") from exc
    if not all(np.isfinite(v) and low <= v <= high for v, (low, high) in zip(values, INPUT_LIMITS)):
        raise ValueError("Una entrada está fuera de los límites de la demo. Revisá los rangos indicados.")
    if float(hours) != int(hours):
        raise ValueError("Las horas de simulación deben ser enteras.")
    climate = dict(zip(["temp_c", "hum_rel_pct", "viento_kmh", "lluvia_mm", "et0_mm_dia"], values[:5]))
    sectors = normalize_sectors(sectors_raw)
    channels = normalize_channels(channels_raw)
    final, history = simulate_sensors(sectors, climate, int(hours))
    quality = DataAgent().validate(final)
    diagnostics = DiagnosticAgent(models).diagnose(final, quality, climate)
    priority = PriorityAgent().propose(diagnostics, values[6])
    audit = ChannelAuditAgent(models).audit(channels, climate, values[5], values[6])
    return {"sectors": final, "history": history, "quality": quality, "priority": priority, "audit": audit}


def add_sector(sectors):
    df = normalize_sectors(sectors)
    if len(df) >= 10:
        raise ValueError("Máximo: 10 sectores. Eliminá uno antes de agregar otro.")
    used = set(df["sector"])
    name = next(f"Sector {letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if f"Sector {letter}" not in used)
    return normalize_sectors(pd.concat([df, pd.DataFrame([new_sector(name)])], ignore_index=True)), name


def remove_sector(sectors, selected):
    df = normalize_sectors(sectors)
    if len(df) <= 1:
        raise ValueError("Debe quedar al menos un sector.")
    if selected not in set(df["sector"]):
        raise ValueError("Elegí un sector existente para eliminar.")
    df = df[df["sector"] != selected].reset_index(drop=True)
    return df, str(df.iloc[0]["sector"])


def input_snapshot(*args):
    sectors = normalize_sectors(args[7]).copy()
    for column in sectors.select_dtypes(include="number"):
        sectors[column] = sectors[column].astype(float)
    channels = normalize_channels(args[8]).copy()
    for column in channels.columns[1:]:
        channels[column] = channels[column].astype(float)
    return ([float(v) for v in args[:7]], sectors.to_json(), channels.to_json(), float(args[9]) if len(args) > 9 else 12.0)
