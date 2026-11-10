"""Explicación con Claude usando un cliente falso: estas pruebas no llaman a la API."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import analyze_inputs
from core import explicacion_ia
from core.synthetic_data import scenario_data


def fake_client(stop_reason="end_turn", text="Revisar Sector E."):
    response = SimpleNamespace(stop_reason=stop_reason, content=[
        SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)])
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))), calls


class ExplicacionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze_inputs(*scenario_data("Falla de sensor"))

    def test_payload_sends_results_without_fabricating_humidity(self):
        payload = json.loads(explicacion_ia.build_payload(self.result, "Falla de sensor"))
        sector = next(row for row in payload["sectores"] if row["sector"] == "Sector C")
        self.assertEqual(sector["humedad_directa"], "NO DISPONIBLE")
        self.assertEqual(len(payload["canales"]), 4)

    def test_returns_model_text(self):
        client, calls = fake_client()
        text = explicacion_ia.explain_turn(self.result, "Falla de sensor", client)
        self.assertEqual(text, "Revisar Sector E.")
        self.assertEqual(calls[0]["model"], explicacion_ia.MODEL)

    def test_refusal_is_reported(self):
        client, _ = fake_client(stop_reason="refusal", text="")
        self.assertIn("no disponible", explicacion_ia.explain_turn(self.result, "Normal", client))

    def test_requires_analysis(self):
        self.assertIn("Analizá", explicacion_ia.explain_turn(None, "Normal"))

    def test_missing_key_keeps_app_working(self):
        with patch.object(explicacion_ia, "load_dotenv"), patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            self.assertIn("falta `ANTHROPIC_API_KEY`", explicacion_ia.explain_turn(self.result, "Normal"))


if __name__ == "__main__":
    unittest.main()
