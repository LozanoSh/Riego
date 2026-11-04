"""Regresión funcional de la etapa Lozano: python -m unittest discover -s tests -v."""
import json
import unittest

import gradio as gr
import numpy as np
import pandas as pd

from app import MODELS, analyze_inputs, feature_importance_figure, human_decision, mark_stale, run_analysis
from core.agents import normalize_sectors
from core.simulation import add_sector, remove_sector
from core.visuals import summary_html
from core.decision import build_protocol_trace, register_human_decision
from core.synthetic_data import build_channel_training_data, build_sector_training_data, scenario_data


class EtapaLozanoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normal = analyze_inputs(*scenario_data("Normal"))

    def test_A_normal(self):
        r = self.normal
        self.assertEqual(len(r["sectors"]), 5)
        self.assertEqual(len(r["audit"]), 4)
        self.assertTrue(r["priority"]["riesgo_deficit_ia_0_100"].between(0, 100).all())
        self.assertTrue(r["audit"]["perdida_ia_pct"].between(0, 100).all())
        self.assertEqual(r["history"]["humedad_suelo_pct"].notna().sum(), 65)
        self.assertTrue((r["history"].groupby("sector")["humedad_suelo_pct"].nunique() > 1).all())

    def test_B_zonda(self):
        zonda = analyze_inputs(*scenario_data("Zonda / estrés"))
        normal_risk = self.normal["priority"].set_index("sector")["riesgo_deficit_ia_0_100"]
        stress_risk = zonda["priority"].set_index("sector")["riesgo_deficit_ia_0_100"]
        self.assertGreater(stress_risk.mean(), normal_risk.mean())
        self.assertTrue((stress_risk.sort_index() >= normal_risk.sort_index()).all())

    def test_B_temperature_wind_only(self):
        args = list(scenario_data("Normal"))
        args[0], args[2] = 40, 42
        result = analyze_inputs(*args)
        self.assertGreater(result["priority"]["riesgo_deficit_ia_0_100"].mean(),
                           self.normal["priority"]["riesgo_deficit_ia_0_100"].mean())

    def test_C_no_sensor(self):
        r = analyze_inputs(*scenario_data("Falla de sensor"))
        sector = r["priority"].set_index("sector").loc["Sector C"]
        self.assertEqual(sector["humedad_directa"], "NO DISPONIBLE")
        self.assertTrue(pd.isna(sector["humedad_medida_pct"]))
        self.assertEqual(sector["confianza"], "BAJA")
        self.assertIn("proxy", sector["modo"])
        self.assertTrue(0 <= sector["riesgo_deficit_ia_0_100"] <= 100)
        readings = r["history"].query("sector == 'Sector C'")
        self.assertTrue(readings[["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]].isna().all().all())
        inputs = json.loads(sector["entradas_modelo"])
        self.assertFalse(set(inputs) & {"humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"})

    def test_D_leak(self):
        args = list(scenario_data("Normal"))
        args[8].loc[1, "indice_fuga_0_1"] = 1.0
        modified = analyze_inputs(*args)["audit"].set_index("tramo").loc["Tramo B"]
        original = self.normal["audit"].set_index("tramo").loc["Tramo B"]
        self.assertGreater(modified["perdida_ia_pct"], original["perdida_ia_pct"])
        self.assertGreater(modified["agua_perdida_l"], original["agua_perdida_l"])

    def test_E_cost_changes_ranking_only(self):
        args = list(scenario_data("Normal"))
        args[8].loc[2, "costo_reparacion_ars"] = 100000.0
        result = analyze_inputs(*args)["audit"]
        self.assertEqual(result.iloc[0]["tramo"], "Tramo C")
        self.assertNotEqual(result.iloc[0]["tramo"], self.normal["audit"].iloc[0]["tramo"])
        pd.testing.assert_series_equal(result.set_index("tramo")["perdida_ia_pct"].sort_index(),
                                       self.normal["audit"].set_index("tramo")["perdida_ia_pct"].sort_index())

    def test_reproducible_generators(self):
        for generate in [build_channel_training_data, build_sector_training_data]:
            a, y = generate()
            b, z = generate()
            pd.testing.assert_frame_equal(a, b)
            np.testing.assert_array_equal(y, z)
        pd.testing.assert_frame_equal(self.normal["history"], analyze_inputs(*scenario_data("Normal"))["history"])

    def test_rain_and_irrigation_raise_moisture(self):
        for change in ["rain", "irrigation"]:
            args = list(scenario_data("Normal"))
            if change == "rain":
                args[3] = 20
            else:
                args[7]["riego_simulado_mm_h"] = 1.5
            wet = analyze_inputs(*args)
            self.assertGreater(wet["sectors"]["humedad_suelo_pct"].mean(), self.normal["sectors"]["humedad_suelo_pct"].mean())
            self.assertLess(wet["priority"]["riesgo_deficit_ia_0_100"].mean(), self.normal["priority"]["riesgo_deficit_ia_0_100"].mean())

    def test_humidity_change_changes_prediction(self):
        args = list(scenario_data("Normal"))
        args[7].loc[0, "humedad_suelo_pct"] = 10
        changed = analyze_inputs(*args)["priority"].set_index("sector").loc["Sector A"]
        base = self.normal["priority"].set_index("sector").loc["Sector A"]
        self.assertGreater(changed["riesgo_deficit_ia_0_100"], base["riesgo_deficit_ia_0_100"])

    def test_climate_factors_affect_sensor(self):
        base = self.normal["sectors"]["humedad_suelo_pct"].mean()
        for index, value in [(0, 40), (2, 42), (4, 9.5)]:
            args = list(scenario_data("Normal"))
            args[index] = value
            self.assertLess(analyze_inputs(*args)["sectors"]["humedad_suelo_pct"].mean(), base)
        args = list(scenario_data("Normal"))
        args[1] = 80
        self.assertGreater(analyze_inputs(*args)["sectors"]["humedad_suelo_pct"].mean(), base)

    def test_all_sensors_disabled(self):
        args = list(scenario_data("Normal"))
        args[7]["sensor_disponible"] = 0
        r = analyze_inputs(*args)
        self.assertTrue(r["history"]["humedad_suelo_pct"].isna().all())
        self.assertTrue(r["priority"]["riesgo_deficit_ia_0_100"].between(0, 100).all())
        self.assertTrue(r["priority"]["confianza"].eq("BAJA").all())

    def test_anomaly_is_discarded(self):
        args = list(scenario_data("Normal"))
        args[7].loc[0, "humedad_suelo_pct"] = 90
        result = analyze_inputs(*args)
        self.assertEqual(result["sectors"].iloc[0]["estado_sensor"], "LECTURA ANÓMALA")
        self.assertTrue(pd.isna(result["sectors"].iloc[0]["humedad_suelo_pct"]))

    def test_missing_ndvi_no_fabricated_prediction(self):
        args = list(scenario_data("Normal"))
        args[7].loc[0, "ndvi"] = np.nan
        result = analyze_inputs(*args)["priority"].set_index("sector").loc["Sector A"]
        self.assertTrue(pd.isna(result["riesgo_deficit_ia_0_100"]))
        self.assertIn("SIN PREDICCIÓN", result["estado"])

    def test_missing_ec_is_not_generated(self):
        args = list(scenario_data("Normal"))
        args[7].loc[0, "ec_ds_m"] = np.nan
        result = analyze_inputs(*args)
        self.assertTrue(result["history"].query("sector == 'Sector A'")["ec_ds_m"].isna().all())
        self.assertIn("proxy", result["priority"].set_index("sector").loc["Sector A", "modo"])

    def test_constraints(self):
        args = list(scenario_data("Normal"))
        args[7].loc[0, "restriccion"] = "No regar"
        result = analyze_inputs(*args)["priority"].set_index("sector").loc["Sector A"]
        self.assertEqual(result["tiempo_sugerido_min"], 0)

    def test_sequential_water_balance(self):
        rows = self.normal["audit"].sort_values("orden_recorrido")
        np.testing.assert_allclose(rows["agua_entrada_l"] - rows["agua_perdida_l"], rows["agua_salida_l"], atol=1)
        np.testing.assert_allclose(rows["agua_salida_l"].to_numpy()[:-1], rows["agua_entrada_l"].to_numpy()[1:])

    def test_importance_comes_from_model(self):
        for model in [MODELS.sector_with_sensor, MODELS.sector_proxy, MODELS.channel_loss]:
            np.testing.assert_allclose(sum(feature_importance_figure(model).data[0].x), 100)
            self.assertGreater(model.n_outputs_, 0)

    def test_sector_limits_and_valid_cost(self):
        with self.assertRaises(ValueError):
            normalize_sectors(scenario_data("Normal")[7].iloc[:0])
        args = list(scenario_data("Normal"))
        args[8].loc[0, "costo_reparacion_ars"] = 0
        with self.assertRaises(ValueError):
            analyze_inputs(*args)

    def test_dynamic_sectors_and_limits(self):
        args = list(scenario_data("Normal"))
        sectors = args[7]
        while len(sectors) < 10:
            sectors, selected = add_sector(sectors)
        args[7] = sectors
        result = analyze_inputs(*args)
        self.assertEqual(len(result["priority"]), 10)
        self.assertEqual(result["history"]["sector"].nunique(), 10)
        self.assertIn('>10 sectores<', summary_html(result, "Personalizado", sectors))
        with self.assertRaises(ValueError):
            add_sector(sectors)
        while len(sectors) > 1:
            sectors, selected = remove_sector(sectors, sectors.iloc[-1]["sector"])
        args[7] = sectors
        result = analyze_inputs(*args)
        self.assertEqual(len(result["priority"]), 1)
        self.assertEqual(set(result["history"]["sector"]), set(sectors["sector"]))
        with self.assertRaises(ValueError):
            remove_sector(sectors, selected)
        for name in ["Normal", "Zonda / estrés", "Falla de sensor", "Canal deteriorado"]:
            self.assertEqual(len(analyze_inputs(*scenario_data(name, sectors))["priority"]), 1)

    def test_deteriorated_channel(self):
        changed = analyze_inputs(*scenario_data("Canal deteriorado"))["audit"].set_index("tramo")
        base = self.normal["audit"].set_index("tramo")
        self.assertGreater(changed.loc["Tramo B", "perdida_ia_pct"], base.loc["Tramo B", "perdida_ia_pct"])

    def test_input_ranges_and_clamps(self):
        args = list(scenario_data("Normal"))
        args[0] = 80
        with self.assertRaises(ValueError):
            analyze_inputs(*args)
        args = list(scenario_data("Normal"))
        args[3] = 40
        args[9] = 48
        r = analyze_inputs(*args)
        self.assertTrue(r["history"]["humedad_suelo_pct"].between(5, 45).all())
        self.assertTrue(r["history"]["temperatura_suelo_c"].between(5, 35).all())
        self.assertTrue(r["history"]["ec_ds_m"].between(0.2, 4.5).all())

    def test_silence_is_pending(self):
        status, _ = register_human_decision("Sin respuesta", "", "")
        self.assertIn("PENDIENTE", status)
        trace = build_protocol_trace(self.normal["priority"], self.normal["quality"], decision="Sin respuesta")
        self.assertEqual(trace.set_index("mensaje").loc["M8", "estado"], "pendiente")

    def test_stale_inputs_block_human_decision(self):
        state, _ = mark_stale()
        with self.assertRaises(gr.Error):
            human_decision("Aceptar", "", "", state)
        outputs = run_analysis(*scenario_data("Normal"))
        args = list(scenario_data("Normal"))
        args[0] = 35
        with self.assertRaises(gr.Error):
            human_decision("Aceptar", "", "", outputs, *args)

    def test_human_decision_and_callback(self):
        outputs = run_analysis(*scenario_data("Normal"))
        self.assertEqual(len(outputs["priority"]), 5)
        for decision, order, note in [("Aceptar", "", ""), ("Modificar", "Sector C primero", "Inspección"), ("Rechazar", "", "Revisar datos")]:
            _, log, trace = human_decision(decision, order, note, outputs, *scenario_data("Normal"))
            self.assertEqual(log.iloc[0]["decision_humana"], decision)
            self.assertEqual(len(trace), 11)


if __name__ == "__main__":
    unittest.main()
