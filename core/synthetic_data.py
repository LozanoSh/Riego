from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .farm import MAP_COLUMNS, normalize_layout

SEED = 42
SECTOR_COLUMNS = [
    "sector", "cultivo", "area_ha", "sensor_disponible", "humedad_suelo_pct",
    "temperatura_suelo_c", "ec_ds_m", "ndvi", "edad_ndvi_dias",
    "dias_desde_ultimo_riego", "turnos_sin_regar", "riego_ultimo_turno",
    "restriccion", "ruido_sensor_pct", "riego_simulado_mm_h",
]
CHANNEL_COLUMNS = [
    "tramo", "longitud_m", "revestido_0_1", "permeabilidad_0_1",
    "indice_fuga_0_1", "sedimento_0_1", "costo_reparacion_ars",
]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_SECTORS = normalize_layout(pd.read_csv(DATA_DIR / "sectores_demo.csv"))
DEFAULT_CHANNELS = pd.read_csv(DATA_DIR / "canales_demo.csv")[CHANNEL_COLUMNS]


def new_sector(name: str) -> dict:
    return dict(zip(SECTOR_COLUMNS, [name, "Vid", 1.0, 1, 27.0, 22.0, 1.2,
                    0.60, 2, 5, 0, 1, "Ninguna", 0.20, 0.0]))


def scenario_data(name: str, sectors=None, channels=None):
    """Presets repetibles, también para fincas de 1–10 sectores."""
    current = DEFAULT_SECTORS if sectors is None else sectors
    rows = []
    for _, row in current.iterrows():
        base = new_sector(str(row["sector"]))
        defaults = DEFAULT_SECTORS[DEFAULT_SECTORS["sector"] == row["sector"]]
        if len(defaults):
            base.update(defaults.iloc[0].to_dict())
        # Los escenarios conservan identidad, cultivo y superficie de sectores agregados.
        base.update({key: row[key] for key in ["sector", "cultivo", "area_ha"] + [c for c in MAP_COLUMNS if c in row]})
        rows.append(base)
    sectors = normalize_layout(pd.DataFrame(rows))
    channels = DEFAULT_CHANNELS.copy(deep=True)
    climate = [24, 40, 12, 0, 5.5, 60, 480]
    if name == "Zonda / estrés":
        climate = [39, 15, 45, 0, 9.5, 60, 480]
        sectors["humedad_suelo_pct"] = (sectors["humedad_suelo_pct"] - 9).clip(5, 45)
        sectors["temperatura_suelo_c"] = 32.0
    elif name == "Falla de sensor":
        target = sectors.index[sectors["sector"] == "Sector C"]
        target = target[0] if len(target) else sectors.index[0]
        sectors.loc[target, "sensor_disponible"] = 0
        sectors.loc[target, ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]] = np.nan
    elif name == "Canal deteriorado":
        channels.loc[1, ["indice_fuga_0_1", "sedimento_0_1"]] = [0.95, 0.70]
    elif name != "Normal":
        raise ValueError("Escenario desconocido")
    return (*climate, sectors, channels, 12)


# Compatibilidad para consumidores de la etapa anterior.
from .sensors import simulate_sensors


def build_channel_training_data(n: int = 6000):
    rng = np.random.default_rng(SEED)
    temp = rng.uniform(0, 42, n)
    rh = rng.uniform(10, 90, n)
    wind = rng.uniform(0, 70, n)
    flow = rng.uniform(0.1, 120, n)
    length = rng.uniform(50, 2000, n)
    lined = rng.integers(0, 2, n)
    permeability = rng.uniform(0, 1.0, n)
    leak = rng.uniform(0, 1, n)
    sediment = rng.uniform(0, 1, n)
    # Verdad sintética: no es una ecuación oficial ni calibrada en campo.
    y = (1.2 + 5 * (1 - lined) + 12 * permeability * (1 - lined)
         + 10 * leak + 4 * sediment + 0.0031 * length * (1 - lined)
         + 1.3 * wind / 45 + 0.8 * np.maximum((temp - 25) / 17, 0)
         + 0.8 * np.maximum((55 - rh) / 55, 0)
         - 0.6 * np.maximum((flow - 120) / 140, 0) + rng.normal(0, 1.1, n))
    X = pd.DataFrame({
        "temp_c": temp, "hum_rel_pct": rh, "viento_kmh": wind,
        "caudal_ls": flow, "longitud_m": length, "revestido": lined,
        "permeabilidad": permeability, "indice_fuga": leak, "sedimento": sediment,
    })
    return X, np.clip(y, 0.5, 48)


def build_sector_training_data(n: int = 7000, with_sensor: bool = True):
    rng = np.random.default_rng(SEED)
    temp = rng.uniform(0, 42, n)
    rh = rng.uniform(10, 90, n)
    wind = rng.uniform(0, 70, n)
    et0 = rng.uniform(1, 12, n)
    ndvi = rng.uniform(0.15, 0.9, n)
    days = rng.uniform(0, 14, n)
    no_irrig = rng.integers(0, 4, n)
    ec = rng.uniform(0.2, 4.5, n)
    soil_temp = rng.uniform(5, 35, n)
    moisture = rng.uniform(5, 45, n)
    risk = (18 + 3.4 * days + 8 * no_irrig + 2.5 * et0 + 0.45 * wind
            + 0.55 * np.maximum(temp - 27, 0)
            + 22 * np.maximum(0.62 - ndvi, 0) - 0.18 * rh)
    data = {
        "temp_c": temp, "hum_rel_pct": rh, "viento_kmh": wind,
        "et0_mm_dia": et0, "ndvi": ndvi, "dias_desde_ultimo_riego": days,
        "turnos_sin_regar": no_irrig,
    }
    if with_sensor:
        risk += (2.2 * np.maximum(30 - moisture, 0)
                 + 4 * np.maximum(ec - 1.8, 0) + 0.8 * np.maximum(soil_temp - 25, 0))
        data.update(ec_ds_m=ec, temperatura_suelo_c=soil_temp, humedad_suelo_pct=moisture)
    risk += rng.normal(0, 4.5 if with_sensor else 7, n)
    return pd.DataFrame(data), np.clip(risk, 0, 100)
