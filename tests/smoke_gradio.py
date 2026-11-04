"""Smoke de la etapa Lozano contra Gradio activo; no es la suite final de entrega."""
import json
import urllib.request
from pathlib import Path
from gradio_client import Client


def main():
    base = "http://127.0.0.1:7860"
    with urllib.request.urlopen(base + "/config", timeout=15) as response:
        config = json.load(response)
    components = {c["id"]: c for c in config["components"]}
    values = {cid: c["props"].get("value") for cid, c in components.items()}
    client = Client(base, verbose=False)

    def cid(label):
        return next(i for i, c in components.items() if c["props"].get("label") == label)

    summary_id = next(i for i, c in components.items() if c["type"] == "html" and "stat-grid" in str(values[i]))
    overview_id = cid("Sectores de la finca · valores iniciales")
    sector_name = cid("Nombre del sector")
    full_priority = cid("Detalle del modelo y priorización")
    repairs = cid("Reparaciones · ranking por litros recuperables / $1000 ARS")
    channels = cid("Características de los canales")

    def call(api):
        dependency = next(d for d in config["dependencies"] if d["api_name"] == api)
        inputs = [i for i in dependency["inputs"] if components[i]["type"] != "state"]
        outputs = [i for i in dependency["outputs"] if components[i]["type"] not in ["state", "button"]]
        result = client.predict(*(values[i] for i in inputs), api_name="/" + api)
        if len(outputs) == 1:
            result = [result]
        for i, value in zip(outputs, result):
            if isinstance(value, dict) and value.get("__type__") == "update":
                if "value" in value:
                    values[i] = value["value"]
            else:
                values[i] = value
        return result

    def rows(table_id):
        table = values[table_id]
        return [dict(zip(table["headers"], row)) for row in table["data"]]

    def count(n):
        assert len(rows(overview_id)) == n
        assert f'"stat-value">{n} sectores<' in values[summary_id]
        assert len(rows(full_priority)) == n

    call("simular")
    count(5)
    call("agregar_sector")
    count(6)
    assert values[sector_name] == "Sector F"
    call("eliminar_sector")
    count(5)
    print("PASS Gradio: agregar y eliminar actualizan ficha, IA, gráfico y resumen")
    for api in ["normal", "zonda", "falla_sensor", "canal_deteriorado"]:
        call(api)
        count(5)
        if api == "falla_sensor":
            row = next(r for r in rows(full_priority) if r["sector"] == "Sector C")
            assert row["humedad_directa"] == "NO DISPONIBLE" and row["confianza"] == "BAJA"
        print("PASS Gradio preset:", api)
    call("normal")
    values[channels]["data"][1][4] = 1.0
    call("simular")
    leak = next(r for r in rows(repairs) if r["Tramo"] == "Tramo B")["Pérdida IA (%)"]
    assert leak > 24.79
    values[channels]["data"][2][6] = 100000
    call("simular")
    assert rows(repairs)[0]["Tramo"] == "Tramo C"
    print("PASS Gradio: fuga y costo modifican resultados")
    values[cid("Temperatura ambiente (°C) · 0–42")] = 38
    call("simular")
    assert len(rows(full_priority)) == 5
    for name in ["Riesgo con sensor", "Riesgo sin sensor", "Pérdidas del canal"]:
        values[cid("Modelo a visualizar")] = name
        call("importancia")
    call("restaurar_base")
    count(5)
    call("decision_humana")
    print("PASS Gradio: clima, tres importancias, restauración y H1 pendiente")
    map_id = next(i for i,c in components.items() if c["type"] == "html" and "farm-main" in c["props"].get("elem_classes", []))
    config_id = cid("Configuración de sectores · completa")
    values[cid("Ver detalle de")] = "Sector B"
    call("seleccionar_sector")
    values[cid("Posición X")] = 60
    values[cid("Canal asociado")] = "canal-d"
    call("simular")
    sector_b = next(r for r in rows(config_id) if r["sector"] == "Sector B")
    assert sector_b["x"] == 60 and sector_b["canal_id"] == "canal-d"
    assert 'data-sector-id="sector-2" data-canal-id="canal-d"' in values[map_id]
    call("agregar_sector")
    assert values[map_id].count('class="farm-sector ') == 6
    path = Path(__file__).resolve().parent.parent / "data" / "finca_config.json"
    backup = path.read_bytes() if path.exists() else None
    try:
        call("guardar_configuracion")
        call("restaurar_finca")
        count(5)
        call("cargar_configuracion")
        count(6)
        sector_b = next(r for r in rows(config_id) if r["sector"] == "Sector B")
        assert sector_b["x"] == 60 and sector_b["canal_id"] == "canal-d"
        call("restaurar_finca")
        count(5)
    finally:
        if backup is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(backup)
    print("PASS Gradio croquis: geometría, conexión, guardar, cargar y restaurar")



if __name__ == "__main__":
    main()
