"""Croquis y persistencia: regresión acotada a la capa visual de Lozano."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from app import analyze_inputs, commit_sector
from core.agents import normalize_sectors
from core.farm import MAP_COLUMNS, apply_geometry, load_farm, save_farm
from core.farm_map import channel_state, farm_map_html, sector_detail_html, sector_state
from core.simulation import add_sector, remove_sector
from core.synthetic_data import SECTOR_COLUMNS, scenario_data


class FarmMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = scenario_data("Normal")
        cls.result = analyze_inputs(*cls.args)

    def test_1_demo_and_channel_associations(self):
        sectors, channels = self.args[7:9]
        html = farm_map_html(sectors, channels, self.result)
        self.assertEqual(html.count('class="farm-sector '), 5)
        self.assertEqual(html.count('class="farm-channel '), 4)
        self.assertEqual(html.count('class="farm-connection"'), 5)
        self.assertIn("60.0 L/s", html)
        self.assertEqual(sectors.set_index("sector").loc["Sector C", "canal_id"], "canal-b")

    def test_2_add_sector_and_model(self):
        args = list(self.args)
        args[7], name = add_sector(args[7])
        r = analyze_inputs(*args)
        html = farm_map_html(args[7], args[8], r)
        self.assertEqual(name, "Sector F")
        self.assertIn('data-sector-name="Sector F"', html)
        self.assertEqual(len(r["priority"]), 6)
        self.assertEqual(r["history"]["sector"].nunique(), 6)

    def test_3_remove_sector(self):
        args = list(self.args)
        args[7], _ = remove_sector(args[7], "Sector C")
        r = analyze_inputs(*args)
        html = farm_map_html(args[7], args[8], r)
        self.assertNotIn('data-sector-name="Sector C"', html)
        self.assertEqual(len(r["priority"]), 4)
        self.assertNotIn("Sector C", set(r["history"]["sector"]))

    def test_4_move_does_not_change_ai(self):
        args = list(self.args)
        args[7] = apply_geometry(args[7], "Sector B", [60, 10, 30, 30, "canal-b"])
        changed = analyze_inputs(*args)
        self.assertIn('data-box="60.0 10.0 30.0 30.0"', farm_map_html(args[7], args[8], changed))
        pd.testing.assert_series_equal(self.result["priority"].set_index("sector")["riesgo_deficit_ia_0_100"].sort_index(),
                                       changed["priority"].set_index("sector")["riesgo_deficit_ia_0_100"].sort_index())

    def test_5_change_channel_and_rename(self):
        args = list(self.args)
        args[7] = apply_geometry(args[7], "Sector B", [54, 8, 34, 25, "canal-d"])
        args[8] = args[8].copy()
        args[8].loc[3, "tramo"] = "Canal del fondo"
        html = farm_map_html(args[7], args[8], self.result)
        self.assertIn('data-sector-id="sector-2" data-canal-id="canal-d"', html)
        self.assertIn("Canal del fondo", sector_detail_html(args[7], args[8], self.result, "Sector B"))
        row = args[7].iloc[1]
        values = [row[c] for c in SECTOR_COLUMNS]
        values[0] = "Lote Norte"
        renamed, _ = commit_sector(args[7], "Sector B", values)
        self.assertEqual(renamed.iloc[1]["sector_id"], row["sector_id"])
        self.assertEqual(renamed.iloc[1]["canal_id"], "canal-d")

    def test_6_prediction_changes_sector_color(self):
        args = list(self.args)
        args[7] = args[7].copy()
        args[7].loc[0, ["humedad_suelo_pct", "dias_desde_ultimo_riego"]] = [40, 0]
        changed = analyze_inputs(*args)
        before = self.result["priority"].set_index("sector").loc["Sector A"]
        after = changed["priority"].set_index("sector").loc["Sector A"]
        self.assertNotEqual(sector_state(before), sector_state(after))
        self.assertEqual(sector_state(after), "low")

    def test_7_channel_loss_changes_color(self):
        args = list(scenario_data("Normal"))
        args[8].loc[1, "indice_fuga_0_1"] = 0
        low = analyze_inputs(*args)["audit"].set_index("tramo").loc["Tramo B", "perdida_ia_pct"]
        args[8].loc[1, "indice_fuga_0_1"] = 1
        high = analyze_inputs(*args)["audit"].set_index("tramo").loc["Tramo B", "perdida_ia_pct"]
        self.assertGreater(high, low)
        self.assertNotEqual(channel_state(low), channel_state(high))

    def test_8_save_and_load(self):
        args = list(scenario_data("Falla de sensor"))
        sectors = apply_geometry(args[7], "Sector B", [60, 12, 30, 30, "canal-d"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "finca.json"
            save_farm(sectors, args[8], path)
            saved = json.loads(path.read_text())
            self.assertIsNone(saved["sectores"][2]["humedad_suelo_pct"])
            loaded, channels = load_farm(path)
            pd.testing.assert_frame_equal(normalize_sectors(sectors), loaded, check_dtype=False)
            self.assertEqual(loaded.iloc[1]["canal_id"], "canal-d")
            self.assertEqual(len(channels), 4)

    def test_9_presets_keep_layout_restore_demo(self):
        moved = apply_geometry(self.args[7], "Sector B", [60, 12, 30, 30, "canal-d"])
        for name in ["Normal", "Zonda / estrés", "Falla de sensor", "Canal deteriorado"]:
            pd.testing.assert_frame_equal(scenario_data(name, moved)[7][MAP_COLUMNS], moved[MAP_COLUMNS])
        demo = scenario_data("Normal")[7]
        self.assertEqual(len(demo), 5)
        self.assertEqual(demo.iloc[1]["x"], 54)
        self.assertEqual(demo.iloc[1]["canal_id"], "canal-b")

    def test_missing_sensor_is_grey_and_never_fabricates(self):
        args = scenario_data("Falla de sensor")
        r = analyze_inputs(*args)
        row = r["priority"].set_index("sector").loc["Sector C"]
        self.assertEqual(sector_state(row), "unknown")
        detail = sector_detail_html(args[7], args[8], r, "Sector C")
        self.assertIn("NO DISPONIBLE", detail)
        self.assertIn("BAJA", detail)
        self.assertIn('risk-unknown', farm_map_html(args[7], args[8], r))

    def test_bounds_and_invalid_config(self):
        with self.assertRaises(ValueError):
            apply_geometry(self.args[7], "Sector B", [90, 10, 30, 30, "canal-b"])
        with self.assertRaises(ValueError):
            apply_geometry(self.args[7], "Sector B", [20, 10, 30, 30, "inventado"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "finca.json"
            path.write_text('{"version": 4}')
            with self.assertRaises(ValueError):
                load_farm(path)

    def test_coincidence_is_not_causality(self):
        detail = sector_detail_html(self.args[7], self.args[8], self.result, "Sector B")
        self.assertIn("Existe coincidencia", detail)
        self.assertIn("No demuestra", detail)


if __name__ == "__main__":
    unittest.main()
