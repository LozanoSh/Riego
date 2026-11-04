from __future__ import annotations

import json
import numpy as np
import pandas as pd

from .ai_models import ModelBundle
from .synthetic_data import SECTOR_COLUMNS, CHANNEL_COLUMNS
from .farm import normalize_layout, CHANNEL_IDS, MAP_COLUMNS


def normalize_sectors(raw) -> pd.DataFrame:
    df = pd.DataFrame(raw).copy()
    # Compatibilidad con los nombres de la versión inicial del MVP.
    df = df.rename(columns={"temp_suelo_c": "temperatura_suelo_c",
                            "dias_desde_riego": "dias_desde_ultimo_riego"})
    if all(isinstance(c, int) for c in df.columns) and len(df.columns) == len(SECTOR_COLUMNS):
        df.columns = SECTOR_COLUMNS
    for column in SECTOR_COLUMNS:
        if column not in df:
            df[column] = np.nan
    if not 1 <= len(df) <= 10:
        raise ValueError("La finca debe tener entre 1 y 10 sectores.")
    for c in SECTOR_COLUMNS:
        if c not in ["sector", "cultivo", "restriccion"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
    _check_names(df, "sector")
    for c in ["sensor_disponible", "riego_ultimo_turno"]:
        if not df[c].isin([0, 1]).all():
            raise ValueError(f"{c} debe ser 0 o 1 en cada sector.")
    for c, low, high in [
        ("area_ha", 0.01, 10000), ("ruido_sensor_pct", 0, 2),
        ("riego_simulado_mm_h", 0, 20), ("turnos_sin_regar", 0, 100),
    ]:
        _check_range(df, c, low, high)
    for c, low, high in [("ndvi", 0.15, 0.90), ("edad_ndvi_dias", 0, 3650),
                         ("dias_desde_ultimo_riego", 0, 14)]:
        _check_range(df, c, low, high, allow_missing=True)
    if not df["restriccion"].isin(["Ninguna", "Inspeccionar", "No regar"]).all():
        raise ValueError("Restricción: usar Ninguna, Inspeccionar o No regar.")
    # No dejar visibles lecturas residuales de una sonda desactivada.
    df.loc[df["sensor_disponible"] == 0,
           ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]] = np.nan
    return normalize_layout(df[SECTOR_COLUMNS + [c for c in MAP_COLUMNS if c in df]])


def _check_names(df, column):
    names = df[column].fillna("").astype(str).str.strip()
    if names.eq("").any() or names.duplicated().any():
        raise ValueError(f"Cada {column} debe tener un nombre único y no vacío.")
    df[column] = names


def _check_range(df, column, low, high, allow_missing=False):
    valid = df[column].between(low, high)
    if allow_missing:
        valid |= df[column].isna()
    if not valid.all():
        raise ValueError(f"{column}: ingresar valores entre {low} y {high}.")


def normalize_channels(raw) -> pd.DataFrame:
    df = pd.DataFrame(raw).copy()
    if len(df.columns) == len(CHANNEL_COLUMNS):
        df.columns = CHANNEL_COLUMNS
    if len(df) != 4 or not set(CHANNEL_COLUMNS).issubset(df.columns):
        raise ValueError("La demostración requiere cuatro tramos con todas sus columnas.")
    _check_names(df, "tramo")
    for c in CHANNEL_COLUMNS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c, low, high in [
        ("longitud_m", 50, 2000), ("revestido_0_1", 0, 1),
        ("permeabilidad_0_1", 0, 1), ("indice_fuga_0_1", 0, 1),
        ("sedimento_0_1", 0, 1), ("costo_reparacion_ars", 100000, 5000000),
    ]:
        _check_range(df, c, low, high)
    if not df["revestido_0_1"].isin([0, 1]).all():
        raise ValueError("Revestimiento debe ser 0 o 1.")
    return df[CHANNEL_COLUMNS].reset_index(drop=True)


class DataAgent:
    """Valida calidad de las lecturas simuladas. No completa datos faltantes."""

    def validate(self, sectors: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, s in sectors.iterrows():
            warnings = []
            level = "ALTA"
            if s["sensor_disponible"] != 1 or s.get("estado_sensor") == "LECTURA ANÓMALA" or pd.isna(s["humedad_suelo_pct"]):
                warnings.append("Sin sensor físico no existe una medición directa de humedad.")
                level = "BAJA"
            if s.get("estado_sensor") == "LECTURA ANÓMALA":
                warnings.append("Lectura anómala descartada: se usa modelo proxy.")
            if pd.isna(s["edad_ndvi_dias"]) or s["edad_ndvi_dias"] > 7:
                warnings.append("Edad de NDVI desconocida o dato desactualizado (>7 días).")
                level = "BAJA"
            for c in ["ndvi", "dias_desde_ultimo_riego"]:
                if pd.isna(s[c]):
                    warnings.append(f"Falta {c}: no se inventa un valor para predecir.")
                    level = "BAJA"
            if s["sensor_disponible"] == 1 and s[["temperatura_suelo_c", "ec_ds_m"]].isna().any():
                warnings.append("Temperatura de suelo o EC no disponible; usar proxy sin esas lecturas.")
                level = "BAJA"
            if s.get("estado_sensor") == "ADVERTENCIA" and level == "ALTA":
                level = "MEDIA"
                warnings.append("Sensor virtual en advertencia: revisar lectura.")
            rows.append({
                "sector": s["sector"], "confianza_datos": level,
                "confianza_num": {"ALTA": 1.0, "MEDIA": 0.7, "BAJA": 0.4}[level],
                "advertencias": " ".join(warnings) if warnings else "Sin advertencias",
            })
        return pd.DataFrame(rows)


class DiagnosticAgent:
    """Predice riesgo, nunca humedad. Usa exactamente las features del modelo."""

    def __init__(self, models: ModelBundle):
        self.models = models

    def diagnose(self, sectors: pd.DataFrame, quality: pd.DataFrame, climate: dict) -> pd.DataFrame:
        out = []
        quality_map = quality.set_index("sector").to_dict("index")
        for _, s in sectors.iterrows():
            direct = s["sensor_disponible"] == 1 and pd.notna(s["humedad_suelo_pct"])
            sensor_model = direct and s[["temperatura_suelo_c", "ec_ds_m"]].notna().all()
            model = self.models.sector_with_sensor if sensor_model else self.models.sector_proxy
            values = {**s.to_dict(), **climate}
            features = {name: values.get(name, np.nan) for name in model.feature_names_in_}
            missing = [k for k, v in features.items() if pd.isna(v)]
            risk = np.nan if missing else float(np.clip(model.predict(pd.DataFrame([features]))[0], 0, 100))
            q = quality_map[s["sector"]]
            if missing:
                status = "SIN PREDICCIÓN — DATOS INSUFICIENTES"
            elif q["confianza_datos"] == "BAJA":
                status = "REVISIÓN HUMANA REQUERIDA"
            else:
                status = "DÉFICIT ALTO" if risk >= 70 else "DÉFICIT MEDIO" if risk >= 45 else "DÉFICIT BAJO"
            evidence = ("Sensor virtual + clima + ET0 + NDVI simulado + historial" if sensor_model
                        else "Proxy: clima + ET0 + NDVI simulado + historial; sin usar humedad, temperatura de suelo ni EC")
            out.append({
                "sector": s["sector"], "riesgo_deficit_ia_0_100": round(risk, 1),
                "estado": status, "modo": "RF con sensor" if sensor_model else "RF sin sensor (proxy)",
                "evidencia": evidence, "confianza": q["confianza_datos"],
                "advertencias": q["advertencias"], "area_ha": float(s["area_ha"]),
                "turnos_sin_regar": int(s["turnos_sin_regar"]), "restriccion": s["restriccion"],
                "sensor_disponible": int(direct),
                "humedad_medida_pct": round(float(s["humedad_suelo_pct"]), 2) if direct else np.nan,
                "humedad_directa": f"{s['humedad_suelo_pct']:.2f}% (VIRTUAL)" if direct else "NO DISPONIBLE",
                "entradas_modelo": json.dumps({k: None if pd.isna(v) else float(v) for k, v in features.items()}, ensure_ascii=False),
            })
        return pd.DataFrame(out)


class PriorityAgent:
    """Reglas transparentes para proponer orden y tiempos; no aprueba el riego."""

    def propose(self, diagnostics: pd.DataFrame, turn_minutes: float) -> pd.DataFrame:
        df = diagnostics.copy()
        bonus = np.minimum(df["turnos_sin_regar"].astype(float), 3) * 8
        df["puntaje_prioridad"] = df["riesgo_deficit_ia_0_100"] + bonus
        df.loc[df["confianza"] == "BAJA", "puntaje_prioridad"] *= 0.55
        df["revision_previa"] = ((df["restriccion"] != "Ninguna") | (df["confianza"] == "BAJA")
                                  | df["riesgo_deficit_ia_0_100"].isna())
        df = df.sort_values(["revision_previa", "puntaje_prioridad"], ascending=[True, False], na_position="last").reset_index(drop=True)
        eligible = (df["restriccion"] == "Ninguna") & df["riesgo_deficit_ia_0_100"].notna() & (df["confianza"] != "BAJA")
        weights = df["puntaje_prioridad"].fillna(0).clip(lower=0) * df["area_ha"] * eligible
        df["tiempo_sugerido_min"] = np.round(weights / weights.sum() * turn_minutes, 1) if weights.sum() else 0.0
        df["orden_propuesto"] = np.arange(1, len(df) + 1)
        df["accion_sugerida"] = np.where(eligible, "Considerar en el plan; requiere H1", "INSPECCIONAR / decisión manual H3")
        df["regla_prioridad"] = "(riesgo IA + 8 × min(turnos sin regar, 3)) × 0.55 si confianza BAJA; revisión previa al final y sin minutos"
        return df[[
            "orden_propuesto", "sector", "humedad_directa", "riesgo_deficit_ia_0_100",
            "confianza", "modo", "estado", "puntaje_prioridad", "tiempo_sugerido_min",
            "restriccion", "accion_sugerida", "evidencia", "advertencias", "entradas_modelo",
            "humedad_medida_pct", "regla_prioridad",
        ]]


class ChannelAuditAgent:
    """Pérdida IA + balance secuencial calculado + ranking económico por regla."""

    def __init__(self, models: ModelBundle):
        self.models = models

    def audit(self, channels: pd.DataFrame, climate: dict, flow_ls: float, turn_minutes: float) -> pd.DataFrame:
        seconds = float(turn_minutes) * 60
        liters = float(flow_ls) * seconds
        rows = []
        for order, (_, row) in enumerate(channels.iterrows(), 1):
            local_flow = liters / seconds
            x = pd.DataFrame([{
                "temp_c": float(climate["temp_c"]), "hum_rel_pct": float(climate["hum_rel_pct"]),
                "viento_kmh": float(climate["viento_kmh"]), "caudal_ls": local_flow,
                "longitud_m": float(row["longitud_m"]), "revestido": int(row["revestido_0_1"]),
                "permeabilidad": float(row["permeabilidad_0_1"]),
                "indice_fuga": float(row["indice_fuga_0_1"]), "sedimento": float(row["sedimento_0_1"]),
            }])
            loss_pct = float(np.clip(self.models.channel_loss.predict(x)[0], 0, 60))
            lost = liters * loss_pct / 100
            recoverable = lost * 0.70  # Hipótesis explícita: reparación recupera 70% de la pérdida local.
            cost = float(row["costo_reparacion_ars"])
            rows.append({
                "orden_recorrido": order, "canal_id": CHANNEL_IDS[order - 1], "tramo": row["tramo"], "perdida_ia_pct": round(loss_pct, 2),
                "caudal_entrada_ls": round(local_flow, 2), "caudal_salida_ls": round((liters - lost) / seconds, 2),
                "agua_entrada_l": round(liters), "agua_perdida_l": round(lost),
                "agua_salida_l": round(liters - lost), "litros_recuperables_si_repara": round(recoverable),
                "costo_reparacion_ars": round(cost), "l_recuperables_por_1000_ars": round(recoverable / cost * 1000, 2),
            })
            liters -= lost
        df = pd.DataFrame(rows)
        df["prioridad_reparacion"] = df["l_recuperables_por_1000_ars"].rank(method="dense", ascending=False).astype(int)
        return df.sort_values(["prioridad_reparacion", "litros_recuperables_si_repara"], ascending=[True, False]).reset_index(drop=True)
