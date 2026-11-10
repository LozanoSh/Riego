"""Informe, propuesta y decisión del módulo IA. No llama a la API ni escribe en data/."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gradio as gr

import app
from core.decision import AGREE, REPAIR_NO, REPAIR_PART, WATER_CHANGE, WATER_PART, decision_record, decisions_view, load_decisions, read_water_edit, save_decision, water_edit_table
from core.explicacion_ia import build_payload, is_unavailable, opine_on_objection
from core.synthetic_data import SECTOR_COLUMNS, scenario_data
from core.visuals import repair_plan_html, water_plan_html


def decide(decision, order="", note="", report="### Datos analizados\nInforme de prueba."):
    data = scenario_data("Normal")
    state = app.run_analysis(*data)
    row = data[7].iloc[0]
    form = [row[c] for c in SECTOR_COLUMNS]
    geometry = [row[c] for c in ["x", "y", "ancho", "alto", "canal_id"]]
    return app.record_current(decision, order, note, report, [], state, data[7], row["sector"], *form, *geometry,
                              *app.settings_from_scenario(data), "Normal")


class DecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = app.analyze_inputs(*scenario_data("Normal"))

    def test_payload_gives_report_its_facts(self):
        payload = json.loads(build_payload(self.result, "Normal"))
        self.assertEqual(payload["umbral_perdida_significativa_pct"], 20)
        self.assertEqual(payload["sectores_con_lectura_de_sonda"], 5)
        self.assertEqual({s["sector"]: s["cultivo"] for s in payload["sectores"]}["Sector C"], "Olivo")
        self.assertTrue(0 < payload["eficiencia_canal_pct"] < 100)
        self.assertIn("70%", payload["supuesto_recuperacion"])

    def test_plan_shows_distribution_losses_and_repair(self):
        html = water_plan_html(self.result) + repair_plan_html(self.result)
        self.assertEqual(html.count("<li>"), 5)
        self.assertIn("Tramo B", html)
        self.assertIn("Tramo D", html)
        self.assertNotIn("Tramo C (", html)
        self.assertIn("$850.000 ARS", html)
        args = list(scenario_data("Normal"))
        args[7].loc[0, "restriccion"] = "No regar"
        self.assertIn("Revisar antes de regar", water_plan_html(app.analyze_inputs(*args)))

    def test_accepted_proposals_are_stored_and_listed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decisiones.json"
            self.assertEqual(load_decisions(path), [])
            save_decision(decision_record("Aceptar", "", "ok", "Normal", self.result, "informe"), path)
            save_decision(decision_record("Modificar", "Sector C primero", "", "Zonda / estrés", self.result), path)
            records = load_decisions(path)
            self.assertEqual(len(records), 2)
            self.assertEqual(len(records[0]["plan"]), 5)
            self.assertEqual(records[0]["informe_ia"], "informe")
            self.assertIsNone(records[1]["informe_ia"])
            view = decisions_view(records)
            self.assertEqual(view.iloc[0]["Decisión"], "Aceptada con cambios")
            self.assertEqual(view.iloc[0]["Plan elegido"], "Sector C primero")
            with self.assertRaises(ValueError):
                save_decision(decision_record("Rechazar", "", "no", "Normal", self.result), path)
            path.write_text("{roto")
            with self.assertRaises(ValueError):
                load_decisions(path)

    def test_accept_saves_reject_does_not(self):
        with patch.object(app, "save_decision") as save, patch.object(app, "decision_history", return_value=decisions_view([])):
            status, _, trace = decide("Aceptar")
            self.assertIn("Guardada", status)
            self.assertEqual(save.call_args.args[0]["informe_ia"], "### Datos analizados\nInforme de prueba.")
            self.assertEqual(trace.set_index("mensaje").loc["M8", "estado"], "registrado")
            decide("Aceptar", report="**Informe no disponible:** falta la key.")
            self.assertIsNone(save.call_args.args[0]["informe_ia"])
            self.assertEqual(save.call_count, 2)
            status, _, _ = decide("Rechazar", note="No coincide con lo que vi en el campo")
            self.assertIn("No se guardó", status)
            decide("Sin respuesta")
            self.assertEqual(save.call_count, 2)
            with self.assertRaises(gr.Error):
                decide("Rechazar")


class FlujoIATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = scenario_data("Normal")
        cls.state = app.run_analysis(*cls.data)

    def run_handler(self, handler, *head):
        row = self.data[7].iloc[0]
        form = [row[c] for c in SECTOR_COLUMNS]
        geometry = [row[c] for c in ["x", "y", "ancho", "alto", "canal_id"]]
        return handler(*head, self.state, self.data[7], row["sector"], *form, *geometry, *app.settings_from_scenario(self.data), "Normal")

    def edited(self, **shift):
        table = water_edit_table(self.state)
        for sector, delta in shift.items():
            table.loc[table["Sector"] == sector.replace("_", " "), "Tus minutos"] += delta
        return table

    def test_consult_reveals_how_and_next_only_with_analysis(self):
        with patch.object(app, "explain_turn", return_value="### Informe"):
            done = app.consult_ia(self.state, "Normal")
            self.assertTrue(done[app.ia_how]["visible"])
            self.assertTrue(done[app.next_button]["visible"])
            self.assertIn("Sector E", done[app.ia_reasoning])
            self.assertNotIn(app.next_button, app.consult_ia(None, "Normal"))

    def test_report_is_split_into_panels_without_losing_text(self):
        titles = ["Datos analizados", "Pérdidas significativas", "Cómo distribuir el agua", "Inversión en reparaciones", "Cómo se llegó a esto", "Datos a revisar"]
        report = "\n".join(f"### {title}\nTexto de {title}" for title in titles)
        with patch.object(app, "explain_turn", return_value=report):
            done = app.consult_ia(self.state, "Normal")
        self.assertEqual(done[app.rep_losses], "Texto de Pérdidas significativas")
        self.assertEqual(done[app.rep_how], "Texto de Cómo se llegó a esto")
        self.assertEqual(done[app.ia_report], report)
        self.assertEqual(done[app.claude_explanation], "")
        with patch.object(app, "explain_turn", return_value="### Otro título\nTexto libre"):
            self.assertIn("Texto libre", app.consult_ia(self.state, "Normal")[app.rep_summary])
        with patch.object(app, "explain_turn", return_value="**Informe no disponible:** sin red."):
            failed = app.consult_ia(self.state, "Normal")
        self.assertIn("no disponible", failed[app.claude_explanation])
        self.assertEqual(failed[app.ia_report], "")
        self.assertIn("Tramo B", failed[app.ia_loss_bars])

    def test_buttons_with_similar_roles_keep_their_own_handlers(self):
        listeners = {}
        for dependency in app.demo.config["dependencies"]:
            for target, _ in dependency["targets"]:
                listeners.setdefault(target, []).append(dependency["api_name"])
        self.assertEqual(app.save_button.value, "APLICAR SECTOR Y ANALIZAR")
        self.assertEqual(app.ia_save_button.value, "GUARDAR EN EL HISTORIAL")
        self.assertIn("guardar_sector", listeners[app.save_button._id])
        self.assertNotIn("guardar_sector", listeners[app.ia_save_button._id])

    def test_steps_swap_inside_the_same_container(self):
        second = app.go_to_step(2)
        self.assertFalse(second[app.ia_step1]["visible"])
        self.assertTrue(app.go_to_step(3)[app.ia_step3]["visible"])
        self.assertTrue(second[app.ia_step2]["visible"])
        self.assertFalse(app.ia_reset()[app.ia_step2]["visible"])

    def test_opinion_is_about_one_part_and_includes_the_edit(self):
        with patch.object(app, "opine_on_objection", return_value="Tenés razón en parte.") as opine:
            done = app.ask_opinion(WATER_PART, "  C ya está regado  ", self.edited(Sector_C=-20, Sector_A=20), "### Informe", [], self.state, "Normal")
        self.assertEqual(opine.call_args.args[3], "C ya está regado")
        self.assertEqual(opine.call_args.kwargs["part"], WATER_PART)
        self.assertEqual(len(opine.call_args.kwargs["proposed"]), 5)
        self.assertEqual(done[app.ia_exchanges][0]["parte"], WATER_PART)
        self.assertIn("C ya está regado", done[app.ia_thread])
        with patch.object(app.gr, "Warning"), patch.object(app, "opine_on_objection") as opine:
            empty = app.ask_opinion(WATER_PART, "   ", self.edited(), "", [], self.state, "Normal")
        opine.assert_not_called()
        self.assertNotIn(app.ia_exchanges, empty)

    def test_controls_follow_each_part(self):
        both = app.on_parts_change(WATER_CHANGE, REPAIR_NO)
        self.assertTrue(both[app.water_edit_box]["visible"])
        self.assertEqual(both[app.objection_part]["choices"], [WATER_PART, REPAIR_PART])
        self.assertEqual(both[app.confirm_button]["value"], app.CONFIRM_REDO)
        agree = app.on_parts_change(AGREE, AGREE)
        self.assertFalse(agree[app.ia_objection]["visible"])
        self.assertEqual(agree[app.confirm_button]["value"], app.CONFIRM_SAVE)

    def test_full_agreement_saves_without_rewriting(self):
        with patch.object(app, "save_decision") as save, patch.object(app, "decision_history", return_value=decisions_view([])), patch.object(app, "revise_report") as revise:
            done = self.run_handler(app.confirm_parts, AGREE, AGREE, self.edited(), "### Informe", [])
        revise.assert_not_called()
        record = save.call_args.args[0]
        self.assertEqual(record["decision"], "Aceptar")
        self.assertEqual(record["partes"]["reparto"]["decision"], "de_acuerdo")
        self.assertFalse(done[app.ia_actions]["visible"])

    def test_partial_disagreement_rewrites_then_saves_each_part(self):
        exchanges = [{"parte": REPAIR_PART, "objecion": "No hay plata este año", "opinion": "Entiendo."}]
        with patch.object(app, "save_decision") as save, patch.object(app, "revise_report", return_value="### Qué decidió el encargado\nRechazó.") as revise:
            done = self.run_handler(app.confirm_parts, WATER_CHANGE, REPAIR_NO, self.edited(Sector_C=-20, Sector_A=20), "### Informe", exchanges)
            save.assert_not_called()
            self.assertTrue(done[app.ia_step3]["visible"])
            parts = done[app.ia_parts]
            self.assertEqual(revise.call_args.args[3], parts)
            self.assertIn("La rechazaste", done[app.ia_comparison])
            self.assertIn("No hay plata", done[app.ia_comparison])
            with patch.object(app, "decision_history", return_value=decisions_view([])):
                closed = self.run_handler(app.save_parts, parts, "### Final", "### Informe", exchanges)
        record = save.call_args.args[0]
        self.assertEqual(record["decision"], "Modificar")
        self.assertEqual(record["orden_modificado"], "Reparto cambiado, reparación rechazada")
        self.assertEqual(record["informe_final"], "### Final")
        by_sector = lambda rows: {r["sector"]: r["minutos"] for r in rows}
        original, final = by_sector(record["partes"]["reparto"]["original"]), by_sector(record["partes"]["reparto"]["final"])
        self.assertAlmostEqual(final["Sector C"], original["Sector C"] - 20, places=0)
        self.assertEqual(final["Sector E"], original["Sector E"])
        self.assertEqual(record["partes"]["reparacion"]["motivo"], "No hay plata este año")
        self.assertIsNone(record["partes"]["reparto"]["motivo"])
        self.assertFalse(closed[app.ia_final_actions]["visible"])

    def test_water_edit_must_be_valid(self):
        with self.assertRaisesRegex(ValueError, "suman"):
            read_water_edit(self.edited(Sector_C=-20), self.state, 480)
        with self.assertRaisesRegex(ValueError, "No cambiaste"):
            read_water_edit(self.edited(), self.state, 480)
        bad = self.edited(Sector_C=-20, Sector_A=20)
        bad.loc[0, "Tus minutos"] = None
        with self.assertRaisesRegex(ValueError, "Completá"):
            read_water_edit(bad, self.state, 480)
        args = list(scenario_data("Normal"))
        args[7].loc[0, "restriccion"] = "No regar"
        blocked = app.analyze_inputs(*args)
        table = water_edit_table(blocked)
        table.loc[table["Sector"] == "Sector A", "Tus minutos"] = 20
        table.loc[table["Sector"] == "Sector E", "Tus minutos"] -= 20
        with self.assertRaisesRegex(ValueError, "No regar"):
            read_water_edit(table, blocked, 480)
        with patch.object(app, "save_decision") as save, patch.object(app, "revise_report") as revise, patch.object(app.gr, "Warning") as warning:
            unanswered = self.run_handler(app.confirm_parts, None, AGREE, self.edited(), "", [])
            unbalanced = self.run_handler(app.confirm_parts, WATER_CHANGE, AGREE, self.edited(Sector_C=-20), "", [])
        save.assert_not_called()
        revise.assert_not_called()
        self.assertEqual(warning.call_count, 2)
        self.assertIn("suman", warning.call_args.args[0])
        for done in [unanswered, unbalanced]:
            self.assertNotIn(app.ia_step3, done)
            self.assertTrue(done[app.confirm_button]["interactive"])

    def test_reject_all_saves_nothing(self):
        with patch.object(app, "save_decision") as save, patch.object(app, "decision_history", return_value=decisions_view([])):
            done = self.run_handler(app.reject_all, "### Informe", [])
        save.assert_not_called()
        self.assertIn("No se guardó", done[app.decision_status])

    def test_opinion_prompt_carries_objection_and_is_labeled_unavailable_on_failure(self):
        class Fake:
            calls = []

            class beta:
                class messages:
                    @staticmethod
                    def create(**kwargs):
                        Fake.calls.append(kwargs)
                        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Opino esto.")])
        self.assertEqual(opine_on_objection(self.state, "Normal", "### Informe", "No me convence", [], Fake), "Opino esto.")
        sent = json.loads(Fake.calls[0]["messages"][0]["content"])
        self.assertEqual(sent["objecion_del_encargado"], "No me convence")
        self.assertIn("regla_prioridad", sent["datos"])
        self.assertTrue(is_unavailable("**Opinión no disponible:** falla."))
        self.assertFalse(is_unavailable("Opino esto."))


if __name__ == "__main__":
    unittest.main()
