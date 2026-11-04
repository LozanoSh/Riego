from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42

def simulate_sensors(sectors: pd.DataFrame, climate: dict, hours: int = 12):
    """Balance didáctico horario, no calibrado agronómicamente. Sin hardware."""
    final = sectors.copy(deep=True)
    for column in ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]:
        final[column] = final[column].astype(float)
    history = []
    for idx, s in sectors.iterrows():
        rng = np.random.default_rng(SEED + sum(map(ord, str(s["sector"]))))
        available = int(s["sensor_disponible"]) == 1
        humidity = float(s["humedad_suelo_pct"])
        soil_temp = float(s["temperatura_suelo_c"])
        ec = float(s["ec_ds_m"])
        anomalous = available and (
            not np.isfinite(humidity) or not 5 <= humidity <= 45
            or (np.isfinite(soil_temp) and not 5 <= soil_temp <= 35)
            or (np.isfinite(ec) and not 0.2 <= ec <= 4.5)
        )
        # ET0 y lluvia son tasas diarias; se convierten a aporte horario.
        drying = (climate["et0_mm_dia"] / 24 * 0.65
                  * (1 + max(climate["temp_c"] - 25, 0) / 50)
                  * (1 + climate["viento_kmh"] / 100)
                  * (1 + (100 - climate["hum_rel_pct"]) / 200))
        wetting = (climate["lluvia_mm"] / 24
                   + float(s["riego_simulado_mm_h"])) * 0.7
        noise = float(s["ruido_sensor_pct"])
        for hour in range(hours + 1):
            state = "NORMAL"
            if not available or anomalous:
                measured, measured_temp, measured_ec = np.nan, np.nan, np.nan
                state = "SIN SENSOR" if not available else "LECTURA ANÓMALA"
            else:
                if hour:
                    humidity = float(np.clip(humidity - drying + wetting, 5, 45))
                    soil_temp = float(np.clip(soil_temp + (climate["temp_c"] - soil_temp) * 0.08, 5, 35))
                    ec = float(np.clip(ec + drying * 0.002 - wetting * 0.005, 0.2, 4.5))
                measured = round(float(np.clip(humidity + rng.normal(0, noise), 5, 45)), 2)
                measured_temp = round(float(np.clip(soil_temp + rng.normal(0, noise * 0.2), 5, 35)), 2)
                measured_ec = round(float(np.clip(ec + rng.normal(0, noise * 0.02), 0.2, 4.5)), 3) if np.isfinite(ec) else np.nan
                if measured < 18 or measured > 45 or not np.isfinite(soil_temp) or not np.isfinite(ec):
                    state = "ADVERTENCIA"
            history.append({
                "sector": s["sector"], "hora": hour,
                "humedad_suelo_pct": measured, "temperatura_suelo_c": measured_temp,
                "ec_ds_m": measured_ec, "estado_sensor": state,
                "origen": "SENSOR VIRTUAL — DATOS DE PRUEBA",
            })
        final.loc[idx, ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]] = [measured, measured_temp, measured_ec]
        final.loc[idx, "estado_sensor"] = state
    return final, pd.DataFrame(history)
