"""Controles de la pestaña Sensores: aplican cambios reales al sector y no inventan lecturas."""
import unittest

import app
from core.synthetic_data import SECTOR_COLUMNS, scenario_data
from core.visuals import sensor_detail


def lab(connected=True, humidity=30.0, hours=12, irrigation=0.0, noise=0.2, sector="Sector A"):
    data = scenario_data("Normal")
    row = data[7].set_index("sector", drop=False).loc[sector]
    form = [row[c] for c in SECTOR_COLUMNS]
    geometry = [row[c] for c in ["x", "y", "ancho", "alto", "canal_id"]]
    settings = app.settings_from_scenario(data)
    settings[8] = hours
    return app.sensor_lab(data[7], sector, *form, *geometry, *settings, "Normal", connected, humidity, irrigation, noise)


class SensorLabTests(unittest.TestCase):
    def test_humidity_slider_changes_reading_and_risk(self):
        dry, wet = lab(humidity=10.0)[app.result_state], lab(humidity=40.0)[app.result_state]
        value = lambda r, table, column: r[table].set_index("sector").loc["Sector A", column]
        self.assertLess(value(dry, "sectors", "humedad_suelo_pct"), value(wet, "sectors", "humedad_suelo_pct"))
        self.assertGreater(value(dry, "priority", "riesgo_deficit_ia_0_100"), value(wet, "priority", "riesgo_deficit_ia_0_100"))

    def test_disconnect_never_fabricates_humidity(self):
        output = lab(connected=False)
        result = output[app.result_state]
        self.assertEqual(result["priority"].set_index("sector").loc["Sector A", "humedad_directa"], "NO DISPONIBLE")
        card = sensor_detail(result, "Sector A")
        self.assertIn("Sonda desconectada", card)
        self.assertIn("NO DISPONIBLE", card)
        self.assertFalse(output[app.lab_connected])

    def test_hours_and_irrigation_apply(self):
        output = lab(hours=24, irrigation=2.0)
        history = output[app.result_state]["history"]
        self.assertEqual(history["hora"].max(), 24)
        readings = history[history["sector"] == "Sector A"]["humedad_suelo_pct"]
        self.assertGreater(readings.iloc[-1], readings.iloc[0])
        self.assertIn("subió", sensor_detail(output[app.result_state], "Sector A"))
        self.assertEqual(output[app.hours], 24)


if __name__ == "__main__":
    unittest.main()
