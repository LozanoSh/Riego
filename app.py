from __future__ import annotations

from functools import partial
from pathlib import Path

import gradio as gr
import numpy as np
import pandas as pd

from core.ai_models import build_models
from core.agents import normalize_channels, normalize_sectors
from core.decision import build_protocol_trace, register_human_decision
from core.farm import apply_geometry, channel_registry, load_farm, overlap_warnings, save_farm
from core.farm_map import farm_map_html, recommendation_html, sector_detail_html
from core.simulation import add_sector, input_snapshot, remove_sector, simulate_turn
from core.synthetic_data import DEFAULT_CHANNELS, DEFAULT_SECTORS, SECTOR_COLUMNS, scenario_data
from core.visuals import (architecture_html, compact_sectors, diagnostic_table, feature_importance_figure,
                          ia_detail, model_description, priority_figure, proposal_view, repair_view, sensor_detail, sensor_twin_figure,
                          summary_html, water_route, sector_cards_html, operational_info)

MODELS = build_models()
CSS_PATH = Path(__file__).resolve().parent / "assets" / "dashboard.css"


def analyze_inputs(*args):
    return simulate_turn(MODELS, *args)


def run_analysis(*args):
    result = analyze_inputs(*args)
    result["inputs"] = input_snapshot(*args)
    return result


def mark_stale():
    return None, "Cambios pendientes. Ejecutá la simulación antes de decidir."


def human_decision(decision, modified_order, note, analysis_state, *current_inputs):
    if analysis_state is None:
        raise gr.Error("Ejecutá la simulación con las entradas actuales antes de registrar H1.")
    if current_inputs:
        try:
            same = analysis_state["inputs"] == input_snapshot(*current_inputs)
        except (ValueError, TypeError):
            same = False
        if not same:
            raise gr.Error("Las entradas cambiaron. Volvé a simular antes de registrar H1.")
    if decision == "Modificar" and not modified_order.strip():
        raise gr.Error("Escribí el nuevo orden humano antes de registrar la modificación.")
    if decision == "Rechazar" and not note.strip():
        raise gr.Error("Indicá el motivo del rechazo.")
    status, log = register_human_decision(decision, modified_order, note)
    trace = build_protocol_trace(analysis_state["priority"], analysis_state["quality"], decision=decision, note=note)
    return status, log, trace


def commit_sector(sectors, selected, values):
    df = pd.DataFrame(sectors).copy()
    if selected not in set(df["sector"]):
        raise ValueError("Elegí un sector existente.")
    row = dict(zip(SECTOR_COLUMNS, values))
    # Las lecturas de una sonda desactivada se descartan, aunque el formulario tuviera valores previos.
    if not row["sensor_disponible"]:
        for column in ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]:
            row[column] = np.nan
    idx = df.index[df["sector"] == selected][0]
    # Asignar columnas completas evita mezclar enteros/decimales en pandas 3.
    records = df.to_dict("records")
    records[idx] = {**records[idx], **row}
    normalized = normalize_sectors(pd.DataFrame(records))
    return normalized, str(normalized.loc[idx, "sector"])


def analysis_args(sectors, settings):
    temp, rh, wind, rain, et0, flow, turn_hours, channels, hours = settings
    return (temp, rh, wind, rain, et0, flow, float(turn_hours) * 60, sectors, channels, hours)


def settings_from_scenario(data):
    return [*data[:6], data[6] / 60, data[8], data[9]]


def form_updates(sectors, selected, channel_rows=None):
    row = sectors.set_index("sector").loc[selected]
    values = {**row.to_dict(), "sector": selected}
    updates = {}
    for column, component in zip(SECTOR_COLUMNS, form_fields):
        value = values[column]
        value = None if pd.isna(value) else value
        if column in ["sensor_disponible", "riego_ultimo_turno"]:
            value = bool(value)
        kwargs = {"value": value}
        if column in ["humedad_suelo_pct", "temperatura_suelo_c", "ec_ds_m"]:
            kwargs["interactive"] = bool(values["sensor_disponible"])
        updates[component] = gr.update(**kwargs)
    for column, component in zip(["x", "y", "ancho", "alto", "canal_id"], geometry_fields):
        kwargs = {"value": values[column]}
        if column == "canal_id":
            kwargs["choices"] = [(r["tramo"], r["canal_id"]) for r in channel_registry(channel_rows if channel_rows is not None else DEFAULT_CHANNELS)]
        updates[component] = gr.update(**kwargs)
    return updates


def render_dashboard(sectors, selected, settings, scenario):
    sectors = normalize_sectors(sectors)
    settings = list(settings)
    settings[7] = normalize_channels(settings[7])
    args = analysis_args(sectors, settings)
    result = run_analysis(*args)
    names = sectors["sector"].tolist()
    if selected not in names:
        selected = names[0]
    p = result["priority"]
    proposal = proposal_view(result)
    output = {
        sectors_state: sectors, result_state: result, scenario_state: scenario,
        sector_selector: gr.update(choices=names, value=selected),
        diagnosis_selector: gr.update(choices=names, value=selected),
        map_selector: gr.update(choices=names, value=selected),
        farm_canvas: farm_map_html(sectors, settings[7], result, selected),
        summary_map: farm_map_html(sectors, settings[7], result, selected, canvas_id="summary"),
        map_detail: sector_detail_html(sectors, settings[7], result, selected),
        map_notice: layout_notice(sectors), sector_config_table: sectors,
        current_recommendation: recommendation_html(result), human_recommendation: recommendation_html(result),
        sector_cards: sector_cards_html(result), operation_info: operational_info(result),
        overview: compact_sectors(sectors), summary_cards: summary_html(result, scenario, sectors),
        diagnosis: diagnostic_table(result), proposal_table: proposal,
        sensor_plot: sensor_twin_figure(result["history"], selected), sensor_reading: sensor_detail(result, selected),
        ai_explanation: ia_detail(result, selected), risk_plot: priority_figure(p),
        audit_table: repair_view(result), audit_detail: result["audit"], water_path: water_route(result["audit"]),
        quality_table: result["quality"], full_priority: p, sensor_history: result["history"],
        trace: build_protocol_trace(p, result["quality"]),
        status: f"**{scenario} · {len(sectors)} sectores · simulación actualizada.** El encargado revisa la propuesta.",
        decision_status: "Decisión H1: PENDIENTE. Las compuertas se operan manualmente.",
        decision_log: pd.DataFrame(), decision: "Sin respuesta", modified_order: "", note: "",
        add_button: gr.update(interactive=len(sectors) < 10),
        remove_button: gr.update(interactive=len(sectors) > 1),
    }
    output.update(form_updates(sectors, selected, settings[7]))
    output.update({component: value for component, value in zip(global_fields, settings)})
    return output


def update_dashboard(action, sectors, selected, *values):
    form_values, geometry, settings, scenario = split_edits(values)
    try:
        if action == "Cargar guardada":
            sectors, saved_channels = load_farm()
            selected = str(sectors.iloc[0]["sector"])
            settings[7], scenario = saved_channels, "Finca guardada"
        elif action in ["Restaurar base", "Cargar demo"]:
            data = scenario_data("Normal")
            sectors, selected = data[7], str(data[7].iloc[0]["sector"])
            settings, scenario = settings_from_scenario(data), "Normal"
        elif action in ["Normal", "Zonda / estrés", "Falla de sensor", "Canal deteriorado"]:
            data = scenario_data(action, sectors)
            sectors, settings, scenario = data[7], settings_from_scenario(data), action
        elif action == "Eliminar":
            sectors, selected = remove_sector(sectors, selected)
            scenario = "Personalizado"
        else:
            sectors, selected = commit_sector(sectors, selected, form_values)
            sectors = apply_geometry(sectors, selected, geometry)
            if action == "Agregar":
                sectors, selected = add_sector(sectors)
                scenario = "Personalizado"
        output = render_dashboard(sectors, selected, settings, scenario)
        if action == "Guardar configuración":
            save_farm(sectors, settings[7])
            output[map_notice] = "**Configuración guardada en `data/finca_config.json`.** " + layout_notice(sectors)
        elif action == "Cargar guardada":
            output[map_notice] = "**Configuración cargada.** Se conserva el clima actual y se recalcula la IA. " + layout_notice(sectors)
        return output
    except (ValueError, TypeError, OSError) as exc:
        raise gr.Error(str(exc)) from exc


def invalidate(sectors, channel_rows=None, selected=None):
    channel_rows = channel_rows if channel_rows is not None else DEFAULT_CHANNELS
    selected = selected if selected in set(sectors["sector"]) else str(sectors.iloc[0]["sector"])
    # Las predicciones anteriores no se presentan como actuales al editar una entrada.
    return {result_state: None, scenario_state: "Personalizado",
            summary_cards: summary_html(None, "Cambios pendientes", sectors),
            farm_canvas: farm_map_html(sectors, channel_rows, None),
            summary_map: farm_map_html(sectors, channel_rows, None, canvas_id="summary"),
            map_detail: sector_detail_html(sectors, channel_rows, None, selected),
            map_notice: "Cambios pendientes. Analizá o guardá la configuración para aplicarlos.",
            current_recommendation: recommendation_html(None), human_recommendation: recommendation_html(None),
            sector_cards: sector_cards_html(None), operation_info: operational_info(None),
            status: "**Cambios pendientes.** Ejecutá la simulación para aplicar el formulario y actualizar los resultados.",
            diagnosis: diagnostic_table(None), proposal_table: pd.DataFrame(),
            sensor_plot: sensor_twin_figure(None), sensor_reading: sensor_detail(None, None),
            ai_explanation: ia_detail(None, None), risk_plot: None, audit_table: pd.DataFrame(),
            water_path: water_route(None), audit_detail: pd.DataFrame(), quality_table: pd.DataFrame(), full_priority: pd.DataFrame(),
            sensor_history: pd.DataFrame(), trace: pd.DataFrame(), decision_log: pd.DataFrame(),
            decision_status: "Resultados pendientes. Volvé a simular antes de registrar H1."}


def select_sector(selected, sectors, result, channel_rows):
    output = form_updates(sectors, selected, channel_rows)
    output.update({sector_selector: gr.update(value=selected), map_selector: gr.update(value=selected),
                   farm_canvas: farm_map_html(sectors, channel_rows, result, selected),
                   summary_map: farm_map_html(sectors, channel_rows, result, selected, canvas_id="summary"),
                   map_detail: sector_detail_html(sectors, channel_rows, result, selected), map_notice: layout_notice(sectors),
                   sensor_plot: sensor_twin_figure(result["history"] if result else None, selected),
                   sensor_reading: sensor_detail(result, selected),
                   diagnosis_selector: gr.update(value=selected), ai_explanation: ia_detail(result, selected)})
    return output


def toggle_sensor(available, sectors, channel_rows, selected):
    output = invalidate(sectors, channel_rows, selected)
    for component, value in [(moisture, 27), (soil_temp, 22), (ec, 1.2)]:
        output[component] = gr.update(value=value if available else None, interactive=bool(available))
    return output


def record_current(decision, order, note, state, sectors, selected, *values):
    try:
        form_values, geometry, settings, _ = split_edits(values)
        current, current_name = commit_sector(sectors, selected, form_values)
        current = apply_geometry(current, current_name, geometry)
        return human_decision(decision, order, note, state, *analysis_args(current, settings))
    except (ValueError, TypeError) as exc:
        raise gr.Error(str(exc)) from exc


def split_edits(values):
    count = len(SECTOR_COLUMNS)
    return list(values[:count]), list(values[count:count + 5]), list(values[count + 5:-1]), values[-1]


def layout_notice(sectors):
    overlaps = overlap_warnings(sectors)
    return ("**Sectores superpuestos:** " + "; ".join(overlaps) + ". Ajustá su distribución."
            if overlaps else "Cuadrícula relativa 0–100. La superficie es declarada; no se calcula desde el croquis.")


def preview_geometry(sectors, selected, channel_rows, result, *geometry):
    try:
        preview = apply_geometry(sectors, selected, geometry)
    except ValueError as exc:
        return {map_notice: f"**Revisá la distribución:** {exc}"}
    return {farm_canvas: farm_map_html(preview, channel_rows, result, selected, preview=True),
            summary_map: farm_map_html(preview, channel_rows, result, selected, preview=True, canvas_id="summary"),
            map_detail: sector_detail_html(preview, channel_rows, result, selected),
            map_notice: "**Vista previa sin aplicar.** Analizar, Aplicar o Guardar incorpora la distribución. " + layout_notice(preview)}


def importance_for(name):
    model = {"Riesgo con sensor": MODELS.sector_with_sensor, "Riesgo sin sensor": MODELS.sector_proxy,
             "Pérdidas del canal": MODELS.channel_loss}[name]
    return feature_importance_figure(model)


def refresh_plot(kind, result, selected, model_name, revision):
    # Gradio dibuja pestañas ocultas a 700px. Al mostrarlas se fuerza el ajuste al panel visible.
    fig = (sensor_twin_figure(result["history"] if result else None, selected)
           if kind == "sensor" else importance_for(model_name))
    fig.update_layout(datarevision=revision + 1)
    return fig, revision + 1


BASE = scenario_data("Normal")
INITIAL = run_analysis(*BASE)
FIRST = str(BASE[7].iloc[0]["sector"])
NAMES = BASE[7]["sector"].tolist()

with gr.Blocks(title="Riego Intrafinca · Mendoza", analytics_enabled=False) as demo:
    sectors_state = gr.State(BASE[7].copy())
    result_state = gr.State(INITIAL)
    scenario_state = gr.State("Normal")
    plot_revision = gr.State(0)
    gr.Markdown("# Asistente Inteligente de Riego Intrafinca\nMendoza · Planificación del turno y revisión de pérdidas.")
    gr.HTML('<div class="demo-banner"><strong>DATOS DE PRUEBA — DEMOSTRACIÓN ACADÉMICA</strong><span>Sensores virtuales y datos sintéticos. El encargado decide; las compuertas se operan manualmente.</span></div>')
    with gr.Row(elem_id="run-toolbar"):
        status = gr.Markdown("**Normal · 5 sectores · análisis inicial disponible.** Configurá la finca y volvé a analizar.")
        run_button = gr.Button("ANALIZAR FINCA", variant="primary", scale=0, min_width=190)

    with gr.Tabs(elem_id="workspace-tabs") as workspace_tabs:
        with gr.Tab("RESUMEN", id="resumen"):
            summary_cards = gr.HTML(summary_html(INITIAL, "Normal", BASE[7]))
            with gr.Row():
                with gr.Column(scale=2, min_width=320):
                    gr.Markdown("## Mapa de la finca")
                    summary_map = gr.HTML(farm_map_html(BASE[7], BASE[8], INITIAL, FIRST, canvas_id="summary"), elem_classes="farm-summary")
                with gr.Column(scale=1, min_width=260):
                    current_recommendation = gr.HTML(recommendation_html(INITIAL))
                    view_map_button = gr.Button("VER MAPA COMPLETO", variant="primary")
                    gr.Markdown("**Límites del MVP:** datos sintéticos, croquis y sensores virtuales; sin validación de campo. La meta del 15% sigue siendo una hipótesis.")

        with gr.Tab("MAPA DE LA FINCA", id="mapa"):
            gr.Markdown("## Mapa de la finca\nCroquis relativo, sin GPS ni imágenes satelitales. Elegí un sector para ver su detalle y configurar la distribución.")
            with gr.Row():
                with gr.Column(scale=3, min_width=330):
                    farm_canvas = gr.HTML(farm_map_html(BASE[7], BASE[8], INITIAL, FIRST), elem_classes="farm-main")
                with gr.Column(scale=1, min_width=280):
                    map_selector = gr.Dropdown(NAMES, value=FIRST, label="Ver detalle de")
                    map_detail = gr.HTML(sector_detail_html(BASE[7], BASE[8], INITIAL, FIRST))
            map_notice = gr.Markdown(layout_notice(BASE[7]))
            gr.Markdown("### Configurar finca\nAplicar, Analizar o Guardar incorpora los cambios del sector elegido. X/Y y tamaño muestran una vista previa inmediata. Aplicá antes de cambiar de sector.")
            with gr.Row():
                add_button = gr.Button("AGREGAR SECTOR")
                remove_button = gr.Button("ELIMINAR SECTOR")
                save_config_button = gr.Button("GUARDAR CONFIGURACIÓN", variant="primary")
            with gr.Row():
                sector_name = gr.Textbox(value=FIRST, label="Nombre del sector")
                crop = gr.Dropdown(["Vid", "Olivo", "Frutal", "Hortaliza"], value="Vid", allow_custom_value=True, label="Cultivo")
                area = gr.Number(value=1.2, minimum=0.01, maximum=10000, label="Superficie (ha)")
                map_channel = gr.Dropdown([(r["tramo"], r["canal_id"]) for r in channel_registry(BASE[8])], value=BASE[7].iloc[0]["canal_id"], label="Canal asociado")
            with gr.Row():
                sensor_available = gr.Checkbox(value=True, label="Sensor virtual disponible")
                moisture = gr.Number(value=30, minimum=5, maximum=45, label="Humedad inicial (%) · 5–45")
                last_irrigation = gr.Checkbox(value=True, label="Regado en el último turno (historial)")
                restriction = gr.Dropdown(["Ninguna", "Inspeccionar", "No regar"], value="Ninguna", label="Restricción")
            with gr.Accordion("CONFIGURACIÓN AVANZADA DEL SECTOR", open=False):
                gr.Markdown("Origen arriba a la izquierda. X aumenta hacia la derecha; Y hacia abajo. La figura debe quedar dentro de 0–100. Ancho y alto: 10–50.")
                with gr.Row():
                    map_x = gr.Number(value=8, minimum=0, maximum=100, label="Posición X")
                    map_y = gr.Number(value=8, minimum=0, maximum=100, label="Posición Y")
                    map_width = gr.Number(value=34, minimum=10, maximum=50, label="Ancho del sector")
                    map_height = gr.Number(value=25, minimum=10, maximum=50, label="Alto del sector")
                with gr.Row():
                    soil_temp = gr.Number(value=21, minimum=5, maximum=35, label="Suelo (°C) · 5–35")
                    ec = gr.Number(value=1, minimum=0.2, maximum=4.5, label="EC (dS/m) · 0,2–4,5")
                    ndvi = gr.Number(value=0.72, minimum=0.15, maximum=0.90, label="NDVI simulado · 0,15–0,90")
                    days = gr.Number(value=3, minimum=0, maximum=14, label="Días desde último riego · 0–14")
                with gr.Row():
                    irrigation = gr.Number(value=0, minimum=0, maximum=20, label="Riego hipotético (mm/h)")
                    noise = gr.Number(value=0.2, minimum=0, maximum=2, label="Ruido (puntos %)")
                    ndvi_age = gr.Number(value=2, minimum=0, maximum=3650, label="Edad NDVI (días)")
                    no_irrigation = gr.Number(value=0, minimum=0, maximum=100, precision=0, label="Turnos sin regar")
                gr.Markdown("El riego es hipotético: no ejecuta ni registra un riego real.")
            save_button = gr.Button("APLICAR SECTOR Y ANALIZAR", variant="primary")
            with gr.Row():
                load_demo_button = gr.Button("CARGAR FINCA DEMO")
                load_config_button = gr.Button("CARGAR CONFIGURACIÓN GUARDADA")
                restore_farm_button = gr.Button("RESTAURAR FINCA DE DEMOSTRACIÓN")
            with gr.Accordion("MVP actual e implementación real futura", open=False):
                gr.Markdown("**MVP actual:** croquis digital + sensor virtual + datos sintéticos → IA → dashboard.\n\n**Implementación real futura:** polígono de finca + sensores físicos + clima + datos satelitales → API → IA → dashboard.\n\nEl MVP valida la arquitectura y la interacción antes de incorporar hardware y georreferenciación real. No demuestra precisión de campo.")

        with gr.Tab("FINCA", id="finca") as finca_tab:
            gr.Markdown("## Finca y sensores\nLecturas virtuales y diagnóstico resumido. La edición de sectores se realiza en Mapa de la finca.")
            sector_cards = gr.HTML(sector_cards_html(INITIAL))
            with gr.Row():
                sector_selector = gr.Dropdown(NAMES, value=FIRST, label="Sector para editar y visualizar")
                edit_map_button = gr.Button("CONFIGURAR EN EL MAPA")
            with gr.Row():
                with gr.Column(scale=1, min_width=280):
                    sensor_reading = gr.HTML(sensor_detail(INITIAL, FIRST))
                with gr.Column(scale=2, min_width=320):
                    sensor_plot = gr.Plot(value=sensor_twin_figure(INITIAL["history"], FIRST), label="Evolución del sector elegido")

        with gr.Tab("CLIMA Y SIMULACIÓN", id="clima"):
            gr.Markdown("## Clima y simulación\nLos presets aplican datos y analizan. Conservan la distribución, nombres y canales asociados de los sectores. Restaurar vuelve a la finca base.")
            with gr.Row():
                normal_button = gr.Button("NORMAL")
                zonda_button = gr.Button("ZONDA / ESTRÉS")
                failure_button = gr.Button("FALLA SENSOR")
                canal_button = gr.Button("CANAL DETERIORADO")
            with gr.Row():
                temp = gr.Number(value=24, minimum=0, maximum=42, label="Temperatura ambiente (°C) · 0–42")
                rh = gr.Number(value=40, minimum=10, maximum=90, label="Humedad relativa (%) · 10–90")
                wind = gr.Number(value=12, minimum=0, maximum=70, label="Viento (km/h) · 0–70")
            with gr.Row():
                rain = gr.Number(value=0, minimum=0, maximum=40, label="Lluvia (mm/día) · 0–40")
                et0 = gr.Number(value=5.5, minimum=1, maximum=12, label="ET0 (mm/día) · 1–12")
                hours = gr.Number(value=12, minimum=0, maximum=48, precision=0, label="Horizonte del sensor (horas) · 0–48")
            gr.Markdown("Lluvia y ET0 se convierten a tasas horarias. El horizonte del sensor es independiente del turno.")
            with gr.Row():
                climate_run = gr.Button("ANALIZAR CON ESTE CLIMA", variant="primary")
                reset_button = gr.Button("RESTAURAR ESCENARIO BASE")

        with gr.Tab("CANALES", id="canales"):
            gr.Markdown("## Canales y pérdidas\nRecorrido lógico del agua y reparación recomendada. La IA predice porcentajes; los volúmenes y el costo-beneficio son cálculos.")
            water_path = gr.HTML(water_route(INITIAL["audit"]))
            operation_info = gr.Markdown(operational_info(INITIAL))
            audit_table = gr.Dataframe(value=repair_view(INITIAL), interactive=False, label="Reparaciones · ranking por litros recuperables / $1000 ARS", max_height=300)
            with gr.Accordion("Editar los cuatro tramos", open=False):
                with gr.Row():
                    flow = gr.Number(value=60, minimum=5, maximum=120, label="Caudal inicial (L/s) · 5–120")
                    turn_hours = gr.Number(value=8, minimum=1, maximum=24, label="Duración del turno (h) · 1–24")
                gr.Markdown("Longitud 50–2000 m; revestido 0/1; índices 0–1; costo $100.000–$5.000.000 ARS. Doble clic para editar. Los identificadores de canal se conservan al renombrar los tramos.")
                channels = gr.Dataframe(value=DEFAULT_CHANNELS, headers=list(DEFAULT_CHANNELS.columns), datatype=["str"] + ["number"] * 6, row_count=4, column_count=7, interactive=True, label="Características de los canales", max_height=260)
            gr.Markdown("**Supuesto:** reparar recupera el 70% de la pérdida local. Litros = caudal × horas × 3600. Rentabilidad = litros recuperables / costo × 1000. Sin validación de campo.")

        with gr.Tab("IA", id="ia") as ia_tab:
            gr.Markdown("## Qué hizo la IA\nRandom Forest estima riesgo con la última lectura virtual. Sin sensor, otro modelo estima riesgo a partir de clima e historial; nunca inventa humedad.")
            diagnosis_selector = gr.Dropdown(NAMES, value=FIRST, label="Sector del diagnóstico")
            ai_explanation = gr.Markdown(ia_detail(INITIAL, FIRST))
            diagnosis = gr.Dataframe(value=diagnostic_table(INITIAL), interactive=False, label="Diagnóstico por sector", max_height=300)
            with gr.Accordion("Variables más importantes", open=True):
                importance_model = gr.Radio(["Riesgo con sensor", "Riesgo sin sensor", "Pérdidas del canal"], value="Riesgo con sensor", label="Modelo a visualizar")
                importance_plot = gr.Plot(value=feature_importance_figure(MODELS.sector_with_sensor), label="Importancia global real del modelo")
            with gr.Accordion("Modelos, métricas y limitaciones", open=False):
                gr.Markdown(model_description(MODELS))
                risk_plot = gr.Plot(value=priority_figure(INITIAL["priority"]), label="Riesgo por sector")

        with gr.Tab("DECISIÓN HUMANA", id="humano"):
            human_recommendation = gr.HTML(recommendation_html(INITIAL))
            gr.Markdown("H1: aceptar, modificar o rechazar. H2: compuertas manuales. H3: inspeccionar, posponer o decidir manualmente ante datos insuficientes. Registro temporal en pantalla.")
            decision_status = gr.Markdown("Decisión H1: PENDIENTE.")
            with gr.Row():
                decision = gr.Dropdown(["Aceptar", "Modificar", "Rechazar", "Sin respuesta"], value="Sin respuesta", label="Decisión del encargado")
                modified_order = gr.Textbox(label="Nuevo orden humano (si modifica)")
            note = gr.Textbox(label="Observación / motivo del rechazo")
            decision_button = gr.Button("REGISTRAR DECISIÓN H1")
            decision_log = gr.Dataframe(interactive=False, label="Registro humano temporal")
            with gr.Accordion("Ver trazabilidad completa", open=False):
                trace = gr.Dataframe(value=build_protocol_trace(INITIAL["priority"], INITIAL["quality"]), interactive=False, label="Trazabilidad temporal existente", max_height=300)

        with gr.Tab("DATOS TÉCNICOS", id="datos"):
            gr.Markdown("## Datos técnicos\nDetalle completo conservado para revisión y defensa. Todos los datos de finca y sensores son de prueba.")
            with gr.Accordion("Sectores y configuración del croquis", open=False):
                sector_config_table = gr.Dataframe(value=BASE[7], interactive=False, label="Configuración de sectores · completa", max_height=300)
                overview = gr.Dataframe(value=compact_sectors(BASE[7]), interactive=False, label="Sectores de la finca · valores iniciales", max_height=280)
            with gr.Accordion("Lecturas horarias y calidad", open=False):
                sensor_history = gr.Dataframe(value=INITIAL["history"], interactive=False, label="Historial virtual", max_height=300)
                quality_table = gr.Dataframe(value=INITIAL["quality"], interactive=False, label="Calidad de los datos")
            with gr.Accordion("Predicciones y prioridades completas", open=False):
                full_priority = gr.Dataframe(value=INITIAL["priority"], interactive=False, label="Detalle del modelo y priorización", max_height=300)
                proposal_table = gr.Dataframe(value=proposal_view(INITIAL), interactive=False, label="Propuesta para revisar", max_height=280)
            with gr.Accordion("Balance completo de canales", open=False):
                audit_detail = gr.Dataframe(value=INITIAL["audit"], interactive=False, label="Balance secuencial calculado", max_height=280)

        with gr.Tab("ARQUITECTURA", id="arquitectura"):
            gr.Markdown("## Cómo funciona\nLa finca organiza sectores y sensores; la IA estima riesgo y pérdidas; el encargado decide.")
            gr.HTML(architecture_html())
            with gr.Row():
                gr.Markdown("### MVP actual\nCroquis digital + sensores virtuales + datos sintéticos → IA → dashboard.")
                gr.Markdown("### Implementación real futura\nPolígono real + sensores físicos + clima + datos satelitales → API → IA → dashboard.")
            gr.Markdown("El MVP valida la arquitectura y la interacción antes de incorporar hardware y georreferenciación real. No hay GIS, GPS, imágenes satelitales ni hardware conectados.\n\n**Limitaciones:** datos sintéticos, sin validación de campo, Sentinel-2 no mide humedad directamente, compuertas manuales y meta del 15% pendiente de validación.")

    form_fields = [sector_name, crop, area, sensor_available, moisture, soil_temp, ec, ndvi, ndvi_age,
                   days, no_irrigation, last_irrigation, restriction, noise, irrigation]
    geometry_fields = [map_x, map_y, map_width, map_height, map_channel]
    global_fields = [temp, rh, wind, rain, et0, flow, turn_hours, channels, hours]
    edit_inputs = [sectors_state, sector_selector] + form_fields + geometry_fields + global_fields + [scenario_state]
    all_outputs = [sectors_state, result_state, scenario_state, sector_selector, diagnosis_selector,
                   overview, summary_cards, diagnosis, proposal_table, sensor_plot, sensor_reading,
                   ai_explanation, risk_plot, audit_table, audit_detail, water_path, quality_table, full_priority,
                   sensor_history, trace, status, decision_status, decision_log, decision, modified_order,
                   note, add_button, remove_button, map_selector, farm_canvas, summary_map, map_detail, map_notice,
                   sector_config_table, current_recommendation, human_recommendation, sector_cards, operation_info] + form_fields + geometry_fields + global_fields
    for button, action, api in [
        (run_button, "Ejecutar", "simular"), (save_button, "Ejecutar", "guardar_sector"),
        (climate_run, "Ejecutar", False), (add_button, "Agregar", "agregar_sector"),
        (remove_button, "Eliminar", "eliminar_sector"), (normal_button, "Normal", "normal"),
        (zonda_button, "Zonda / estrés", "zonda"), (failure_button, "Falla de sensor", "falla_sensor"),
        (canal_button, "Canal deteriorado", "canal_deteriorado"), (reset_button, "Restaurar base", "restaurar_base"),
        (restore_farm_button, "Restaurar base", "restaurar_finca"), (load_demo_button, "Cargar demo", "cargar_demo"),
        (save_config_button, "Guardar configuración", "guardar_configuracion"),
        (load_config_button, "Cargar guardada", "cargar_configuracion"),
    ]:
        button.click(partial(update_dashboard, action), inputs=edit_inputs, outputs=all_outputs, api_name=api, concurrency_id="dashboard", concurrency_limit=1)
    for field in form_fields + global_fields:
        if field is not sensor_available:
            field.input(invalidate, inputs=[sectors_state, channels, sector_selector], outputs=all_outputs, queue=False, api_name=False)
    for field in geometry_fields:
        field.input(preview_geometry, inputs=[sectors_state, sector_selector, channels, result_state] + geometry_fields,
                    outputs=all_outputs, api_name=False, concurrency_id="dashboard")
    sensor_available.input(toggle_sensor, inputs=[sensor_available, sectors_state, channels, sector_selector], outputs=all_outputs, queue=False, api_name=False)
    for selector in [sector_selector, map_selector]:
        selector.input(select_sector, inputs=[selector, sectors_state, result_state, channels], outputs=all_outputs, api_name="seleccionar_sector" if selector is map_selector else False)
    diagnosis_selector.input(ia_detail, inputs=[result_state, diagnosis_selector], outputs=ai_explanation, api_name=False)
    importance_model.change(importance_for, inputs=importance_model, outputs=importance_plot, api_name="importancia")
    for tab, kind, plot in [(finca_tab, "sensor", sensor_plot), (ia_tab, "importance", importance_plot)]:
        tab.select(partial(refresh_plot, kind), inputs=[result_state, sector_selector, importance_model, plot_revision], outputs=[plot, plot_revision], api_name=False)
    for button in [view_map_button, edit_map_button]:
        button.click(lambda: gr.update(selected="mapa"), outputs=workspace_tabs, api_name=False)
    decision_button.click(record_current, inputs=[decision, modified_order, note, result_state] + edit_inputs,
                          outputs=[decision_status, decision_log, trace], api_name="decision_humana")
    gr.Markdown("Etapa 1 · Lozano → Siccardi → Sosa → Rivamar. Uso de IA: ChatGPT como apoyo; el equipo debe verificar supuestos y decisiones antes de entregar.")

if __name__ == "__main__":
    demo.launch(inbrowser=True, server_name="127.0.0.1", share=False,
                theme=gr.themes.Default(primary_hue="emerald", secondary_hue="sky", neutral_hue="slate",
                                        font_mono=["Source Sans Pro", "Arial", "sans-serif"]).set(
                    button_primary_background_fill="#216c50", button_primary_background_fill_hover="#19543e",
                    button_primary_background_fill_dark="#235e44", button_primary_text_color="#ffffff",
                    block_label_text_color="#536961", block_label_text_color_dark="#a8b9b0"),
                css=CSS_PATH.read_text())
