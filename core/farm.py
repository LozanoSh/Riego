"""Croquis normalizado y configuración local. No modifica modelos ni calcula áreas GIS."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd

CHANNEL_IDS = ("canal-a", "canal-b", "canal-c", "canal-d")
MAP_COLUMNS = ["sector_id", "x", "y", "ancho", "alto", "canal_id"]
CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "finca_config.json"
DEMO_BOXES = [(8, 8, 34, 25), (54, 8, 34, 25), (8, 41, 34, 25), (54, 41, 34, 25), (31, 74, 34, 20)]
DEMO_CHANNELS = ["canal-a", "canal-b", "canal-b", "canal-c", "canal-d"]


def channel_registry(channels):
    from .synthetic_data import CHANNEL_COLUMNS
    df = pd.DataFrame(channels).copy()
    if len(df.columns) == len(CHANNEL_COLUMNS):
        df.columns = CHANNEL_COLUMNS
    if not set(CHANNEL_COLUMNS).issubset(df.columns):
        raise ValueError("Faltan columnas del canal. Cargá la demo o completá los cuatro tramos.")
    return [{"canal_id": cid, **row} for cid, row in zip(CHANNEL_IDS, df[CHANNEL_COLUMNS].to_dict("records"))]


def boxes_overlap(a, b):
    return (a[0] < b[0] + b[2] and a[0] + a[2] > b[0]
            and a[1] < b[1] + b[3] and a[1] + a[3] > b[1])


def free_box(occupied):
    for y in range(2, 85, 2):
        for x in range(2, 81, 2):
            candidate = (x, y, 18, 14)
            if not any(boxes_overlap(candidate, box) for box in occupied):
                return candidate
    return (5, 5, 18, 14)  # Se avisa superposición; no se desplaza el diseño del usuario.


def normalize_layout(sectors):
    df = pd.DataFrame(sectors).copy().reset_index(drop=True)
    had_layout = all(c in df for c in ["x", "y", "ancho", "alto"])
    for column in MAP_COLUMNS:
        if column not in df:
            df[column] = None
    used = set(df["sector_id"].dropna().astype(str))
    occupied = []
    for _, row in df.iterrows():
        try:
            box = tuple(float(row[c]) for c in ["x", "y", "ancho", "alto"])
            if all(math.isfinite(v) for v in box):
                occupied.append(box)
        except (ValueError, TypeError):
            pass
    for i, row in df.iterrows():
        if pd.isna(row["sector_id"]):
            sid = next(f"sector-{n}" for n in range(1, 100) if f"sector-{n}" not in used)
            df.at[i, "sector_id"] = sid
            used.add(sid)
        if all(pd.isna(row[c]) for c in ["x", "y", "ancho", "alto"]):
            box = DEMO_BOXES[i] if not had_layout and len(df) <= 5 else free_box(occupied)
            for column, value in zip(["x", "y", "ancho", "alto"], box):
                df.at[i, column] = value
            occupied.append(box)
        if pd.isna(row["canal_id"]):
            df.at[i, "canal_id"] = DEMO_CHANNELS[i] if not had_layout and i < 5 else CHANNEL_IDS[i % 4]
    if df["sector_id"].astype(str).str.strip().eq("").any() or df["sector_id"].duplicated().any():
        raise ValueError("Los identificadores de sector deben ser únicos y no vacíos.")
    for column in ["x", "y", "ancho", "alto"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype(float)
        if not df[column].map(math.isfinite).all():
            raise ValueError("Completá X, Y, ancho y alto con números válidos.")
    if not (df["x"].between(0, 100) & df["y"].between(0, 100)
            & df["ancho"].between(10, 50) & df["alto"].between(10, 50)
            & (df["x"] + df["ancho"] <= 100) & (df["y"] + df["alto"] <= 100)).all():
        raise ValueError("El sector debe quedar dentro de 0–100; ancho y alto: 10–50. X + ancho e Y + alto no pueden superar 100.")
    if not df["canal_id"].isin(CHANNEL_IDS).all():
        raise ValueError("Elegí uno de los cuatro canales disponibles.")
    return df


def apply_geometry(sectors, selected, values):
    df = normalize_layout(sectors)
    matches = df.index[df["sector"] == selected]
    if not len(matches):
        raise ValueError("Elegí un sector existente.")
    for column, value in zip(["x", "y", "ancho", "alto", "canal_id"], values):
        if column == "canal_id":
            df.at[matches[0], column] = value
        else:
            try:
                df.at[matches[0], column] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Completá la geometría antes de aplicar.") from exc
    return normalize_layout(df)


def overlap_warnings(sectors):
    rows = pd.DataFrame(sectors).to_dict("records")
    warnings = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if boxes_overlap(tuple(a[k] for k in ["x", "y", "ancho", "alto"]),
                             tuple(b[k] for k in ["x", "y", "ancho", "alto"])):
                warnings.append(f"{a['sector']} / {b['sector']}")
    return warnings


def save_farm(sectors, channels, path=CONFIG_PATH):
    from .agents import normalize_channels, normalize_sectors
    sectors = normalize_sectors(sectors)
    channels = normalize_channels(channels)
    config = {"version": 1, "nombre": "Finca Demo", "sistema_coordenadas": "croquis relativo 0–100; no georreferenciado",
              "sectores": json.loads(sectors.to_json(orient="records")), "canales": channel_registry(channels)}
    encoded = json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            out.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path


def load_farm(path=CONFIG_PATH):
    from .agents import normalize_channels, normalize_sectors
    from .synthetic_data import SECTOR_COLUMNS
    path = Path(path)
    if not path.exists():
        raise ValueError("Todavía no hay una configuración guardada. Guardá la finca o cargá la demostración.")
    if path.stat().st_size > 256000:
        raise ValueError("La configuración supera el tamaño permitido para este MVP.")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("version") != 1:
            raise ValueError("Versión de configuración no compatible.")
        rows, channel_rows = config["sectores"], config["canales"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 10:
            raise ValueError("La configuración debe contener entre uno y diez sectores.")
        if not all(isinstance(row, dict) and set(SECTOR_COLUMNS + MAP_COLUMNS).issubset(row) for row in rows):
            raise ValueError("La configuración de sectores está incompleta.")
        if not isinstance(channel_rows, list) or len(channel_rows) != 4:
            raise ValueError("Se requieren cuatro tramos de canal.")
        if [row.get("canal_id") for row in channel_rows] != list(CHANNEL_IDS):
            raise ValueError("Los identificadores de los canales no coinciden con el recorrido.")
        sectors = normalize_sectors(pd.DataFrame(rows))
        channels = normalize_channels(pd.DataFrame(channel_rows).drop(columns="canal_id"))
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("El archivo de configuración no es válido; la finca actual no se modificó.") from exc
    return sectors, channels
