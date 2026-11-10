from __future__ import annotations

from functools import partial
import json
from pathlib import Path

import gradio as gr
import numpy as np
import pandas as pd

from core.ai_models import build_models
from core.agents import normalize_channels, normalize_sectors
from core.decision import (AGREE, EDIT_COLUMNS, REPAIR_NO, REPAIR_PART, SAVED_DECISIONS, WATER_CHANGE, WATER_PART, build_parts, parts_changed, parts_summary, water_edit_table, build_protocol_trace, decision_record, decisions_view, load_decisions,
                           register_human_decision, save_decision)
from core.explicacion_ia import explain_turn, is_unavailable, opine_on_objection, revise_report, split_report
from core.farm import apply_geometry, channel_registry, load_farm, overlap_warnings, save_farm
from core.farm_map import farm_map_html, recommendation_html, sector_detail_html
from core.simulation import add_sector, input_snapshot, remove_sector, simulate_turn
from core.synthetic_data import DEFAULT_CHANNELS, DEFAULT_SECTORS, SECTOR_COLUMNS, scenario_data
from core.visuals import (diagnostic_table, feature_importance_figure,
                          ia_detail, ia_stepper_html, loss_bars_html, model_description, reasoning_html, parts_comparison_html, repair_cards_html, repair_plan_html, report_kpis_html, water_bars_html, water_plan_html, priority_figure, repair_view, sensor_detail, sensor_twin_figure,
                          summary_html, water_route, sector_cards_html, operational_info)

MODELS = build_models()
CSS_PATH = Path(__file__).resolve().parent / "assets" / "dashboard.css"
CONFIRM_SAVE, CONFIRM_REDO = "CONFIRMAR Y GUARDAR", "REHACER EL INFORME CON MIS CAMBIOS"


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
    output = {
        sectors_state: sectors, result_state: result, scenario_state: scenario,
        sector_selector: gr.update(choices=names, value=selected),
        diagnosis_selector: gr.update(choices=names, value=selected),
        map_selector: gr.update(choices=names, value=selected),
        farm_canvas: farm_map_html(sectors, settings[7], result, selected),
        summary_map: farm_map_html(sectors, settings[7], result, selected, canvas_id="summary"),
        map_detail: sector_detail_html(sectors, settings[7], result, selected),
        map_notice: layout_notice(sectors),
        current_recommendation: recommendation_html(result), human_recommendation: water_plan_html(result), repair_summary: repair_plan_html(result),
        sector_cards: sector_cards_html(result), operation_info: operational_info(result),
        summary_cards: summary_html(result, scenario, sectors),
        diagnosis: diagnostic_table(result),
        sensor_plot: sensor_twin_figure(result["history"], selected), sensor_reading: sensor_detail(result, selected),
        ai_explanation: ia_detail(result, selected), risk_plot: priority_figure(p),
        audit_table: repair_view(result), water_path: water_route(result["audit"]),
        status: f"**{scenario} · {len(sectors)} sectores · simulación actualizada.** El encargado revisa la propuesta.",
        decision_log: decision_history(),
        add_button: gr.update(interactive=len(sectors) < 10),
        remove_button: gr.update(interactive=len(sectors) > 1),
    }
    output.update(form_updates(sectors, selected, settings[7]))
    output.update({component: value for component, value in zip(global_fields, settings)})
    output.update(lab_updates(sectors, selected))
    output.update(ia_reset())
    return output


def lab_updates(sectors, selected):
    row = sectors.set_index("sector").loc[selected]
    connected = bool(row["sensor_disponible"])
    humidity = row["humedad_suelo_pct"]
    return {lab_connected: connected,
            lab_humidity: gr.update(value=27.0 if pd.isna(humidity) else float(np.clip(humidity, 5, 45)), interactive=connected),
            lab_irrigation: float(row["riego_simulado_mm_h"]), lab_noise: float(row["ruido_sensor_pct"])}


def sensor_lab(sectors, selected, *values):
    """Aplica los controles de la sonda al sector elegido y vuelve a analizar toda la finca."""
    edits, (connected, humidity, irrigation_rate, noise_level) = list(values[:-4]), values[-4:]
    at = SECTOR_COLUMNS.index
    edits[at("sensor_disponible")] = bool(connected)
    if connected:
        edits[at("humedad_suelo_pct")] = humidity
        # Al reconectar una sonda sin lecturas previas se usan los mismos valores iniciales que en el mapa.
        for column, default in [("temperatura_suelo_c", 22), ("ec_ds_m", 1.2)]:
            if edits[at(column)] is None:
                edits[at(column)] = default
    edits[at("ruido_sensor_pct")], edits[at("riego_simulado_mm_h")] = noise_level, irrigation_rate
    return update_dashboard("Ejecutar", sectors, selected, *edits)


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
            current_recommendation: recommendation_html(None), human_recommendation: water_plan_html(None), repair_summary: repair_plan_html(None),
            sector_cards: sector_cards_html(None), operation_info: operational_info(None),
            status: "**Cambios pendientes.** Ejecutá la simulación para aplicar el formulario y actualizar los resultados.",
            diagnosis: diagnostic_table(None),
            sensor_plot: sensor_twin_figure(None), sensor_reading: sensor_detail(None, None),
            ai_explanation: ia_detail(None, None), risk_plot: None, audit_table: pd.DataFrame(),
            water_path: water_route(None), decision_log: decision_history(), **ia_reset(),
            decision_status: "Hay cambios sin analizar. Volvé a analizar la finca antes de decidir."}


def select_sector(selected, sectors, result, channel_rows):
    output = form_updates(sectors, selected, channel_rows)
    output.update({sector_selector: gr.update(value=selected), map_selector: gr.update(value=selected),
                   farm_canvas: farm_map_html(sectors, channel_rows, result, selected),
                   summary_map: farm_map_html(sectors, channel_rows, result, selected, canvas_id="summary"),
                   map_detail: sector_detail_html(sectors, channel_rows, result, selected), map_notice: layout_notice(sectors),
                   sensor_plot: sensor_twin_figure(result["history"] if result else None, selected),
                   sensor_reading: sensor_detail(result, selected),
                   diagnosis_selector: gr.update(value=selected), ai_explanation: ia_detail(result, selected)})
    output.update(lab_updates(sectors, selected))
    return output


def toggle_sensor(available, sectors, channel_rows, selected):
    output = invalidate(sectors, channel_rows, selected)
    for component, value in [(moisture, 27), (soil_temp, 22), (ec, 1.2)]:
        output[component] = gr.update(value=value if available else None, interactive=bool(available))
    return output


def decision_history():
    try:
        return decisions_view(load_decisions())
    except ValueError:
        return decisions_view([])


def ia_reset():
    """Cada análisis nuevo vuelve al comienzo: un informe viejo no se puede aceptar sobre datos nuevos."""
    return {ia_stepper: ia_stepper_html(1), ia_step1: gr.update(visible=True), ia_step2: gr.update(visible=False), ia_step3: gr.update(visible=False),
            claude_explanation: "", ia_report: "", ia_how: gr.update(visible=False), next_button: gr.update(visible=False),
            explain_button: gr.update(value="CONSULTAR A LA IA", interactive=True), ia_exchanges: [], ia_parts: None,
            water_choice: gr.update(value=None, interactive=True), repair_choice: gr.update(value=None, interactive=True),
            water_edit_box: gr.update(visible=False), human_recommendation: gr.update(visible=True), ia_actions: gr.update(visible=True),
            ia_objection: gr.update(visible=False), objection_part: gr.update(choices=[], value=None), confirm_button: gr.update(value=CONFIRM_SAVE, interactive=True),
            ia_final_actions: gr.update(visible=True), ia_final_report: "", decision_final_status: "",
            ia_thread: "", objection_text: "", decision_status: ""}


def start_consult():
    return {claude_explanation: "**La IA está analizando la finca.** Puede tardar hasta un minuto.",
            explain_button: gr.update(interactive=False), ia_how: gr.update(visible=False), next_button: gr.update(visible=False)}


def consult_ia(result, scenario, hours=8):
    report = explain_turn(result, scenario)
    if result is None:
        return {claude_explanation: report, explain_button: gr.update(interactive=True)}
    failed = is_unavailable(report)
    sections = split_report(report)
    # Si faltara algún título, el informe entero va a Resumen para no perder nada.
    summary = sections.get("Datos analizados", "" if failed else report)
    return {claude_explanation: report if failed else "", ia_report: "" if failed else report,
            rep_summary: summary, rep_review: sections.get("Datos a revisar", ""), rep_losses: sections.get("Pérdidas significativas", ""),
            rep_water: sections.get("Cómo distribuir el agua", ""), rep_repairs: sections.get("Inversión en reparaciones", ""),
            rep_how: sections.get("Cómo se llegó a esto", ""), ia_kpis: report_kpis_html(result), ia_loss_bars: loss_bars_html(result),
            ia_water_bars: water_bars_html(result), ia_repairs: repair_cards_html(result), ia_reasoning: reasoning_html(result),
            water_edit: water_edit_table(result), water_total: water_total_text(water_edit_table(result), hours), ia_how: gr.update(visible=True), next_button: gr.update(visible=True),
            explain_button: gr.update(value="VOLVER A CONSULTAR", interactive=True)}


def go_to_step(step):
    return {ia_stepper: ia_stepper_html(step), ia_step1: gr.update(visible=step == 1), ia_step2: gr.update(visible=step == 2), ia_step3: gr.update(visible=step == 3)}


def on_parts_change(water, repair):
    changing = water == WATER_CHANGE
    parts = [name for name, disagreed in [(WATER_PART, changing), (REPAIR_PART, repair == REPAIR_NO)] if disagreed]
    return {water_edit_box: gr.update(visible=changing), human_recommendation: gr.update(visible=not changing), ia_objection: gr.update(visible=bool(parts)),
            objection_part: gr.update(choices=parts, value=parts[0] if parts else None),
            confirm_button: gr.update(value=CONFIRM_REDO if parts else CONFIRM_SAVE, interactive=True)}


def water_total_text(table, hours):
    minutes = pd.to_numeric(pd.DataFrame(table).get(EDIT_COLUMNS[2]), errors="coerce").fillna(0).sum()
    turn = float(hours) * 60
    return f"**Total: {minutes:.0f} de {turn:.0f} minutos del turno.**" + ("" if abs(minutes - turn) <= 1 else " Ajustá los minutos para que coincidan.")


def start_opinion():
    return {send_objection: gr.update(value="LA IA ESTÁ RESPONDIENDO", interactive=False)}


def thread_markdown(exchanges):
    return "\n\n---\n\n".join(f"**Vos, sobre {e['parte'].lower()}:** {e['objecion']}\n\n**IA:**\n\n{e['opinion']}" for e in exchanges)


def ask_opinion(part, objection, table, report, exchanges, result, scenario):
    done = {send_objection: gr.update(value="PEDIR OPINIÓN A LA IA", interactive=True)}
    if not (objection or "").strip():
        gr.Warning("Escribí qué no te convence antes de enviarlo.")
        return done
    previous = [e for e in exchanges if not is_unavailable(e["opinion"])]
    proposed = None
    if part == WATER_PART:
        proposed = json.loads(pd.DataFrame(table)[[EDIT_COLUMNS[0], EDIT_COLUMNS[2]]].to_json(orient="records", force_ascii=False))
    opinion = opine_on_objection(result, scenario, report or "", objection.strip(), previous, part=part, proposed=proposed)
    exchanges = exchanges + [{"parte": part, "objecion": objection.strip(), "opinion": opinion}]
    return {**done, ia_exchanges: exchanges, ia_thread: thread_markdown(exchanges), objection_text: ""}


def closed_controls():
    return {ia_actions: gr.update(visible=False), ia_objection: gr.update(visible=False), water_edit_box: gr.update(visible=False),
            human_recommendation: gr.update(visible=True), water_choice: gr.update(interactive=False), repair_choice: gr.update(interactive=False)}


def start_confirm():
    return {confirm_button: gr.update(value="PROCESANDO", interactive=False)}


def warn(message, output):
    """Un dato inválido se avisa sin error: gr.Error tapa todos los componentes y deja trabado el botón."""
    gr.Warning(message)
    return output


def confirm_parts(water, repair, table, report, exchanges, state, sectors, selected, *values):
    restored = {confirm_button: gr.update(interactive=True)}
    if state is None:
        return warn("Hay cambios sin analizar. Volvé a analizar la finca antes de decidir.", restored)
    if water is None or repair is None:
        return warn("Respondé las dos partes antes de confirmar.", restored)
    try:
        _, _, settings, scenario = split_edits(values)
        parts = build_parts(water, repair, table, exchanges, state, float(settings[6]) * 60)
        if parts_changed(parts):
            # La validación del registro se adelanta para no gastar una consulta sobre datos desactualizados.
            current, name = commit_sector(sectors, selected, split_edits(values)[0])
            if state["inputs"] != input_snapshot(*analysis_args(apply_geometry(current, name, split_edits(values)[1]), settings)):
                return warn("Las entradas cambiaron. Volvé a analizar la finca antes de decidir.", restored)
        else:
            _, history, _ = record_current("Aceptar", "", "", report, exchanges, state, sectors, selected, *values, parts=parts)
            return {**closed_controls(), decision_status: "**Propuesta aceptada y guardada en el historial.** Las compuertas se operan a mano.",
                    decision_log: history, ia_history: gr.update(open=True)}
    except gr.Error as exc:
        return warn(exc.message, restored)
    except (ValueError, TypeError) as exc:
        return warn(str(exc), restored)
    return {**go_to_step(3), ia_parts: parts, ia_comparison: parts_comparison_html(parts), decision_final_status: "",
            ia_final_report: revise_report(state, scenario, report or "", parts, exchanges), ia_final_actions: gr.update(visible=True)}


def save_parts(parts, final_report, report, exchanges, state, sectors, selected, *values):
    try:
        _, history, _ = record_current("Modificar", parts_summary(parts), "", report, exchanges, state, sectors, selected, *values, parts=parts, final_report=final_report)
    except gr.Error as exc:
        return warn(exc.message, {decision_final_status: ""})
    return {**closed_controls(), decision_final_status: "**Guardado en el historial con tus cambios.** Las compuertas se operan a mano.",
            decision_log: history, ia_final_actions: gr.update(visible=False), ia_history: gr.update(open=True)}


def reject_all(report, exchanges, state, sectors, selected, *values):
    reason = exchanges[-1]["objecion"] if exchanges else "Sin motivo indicado"
    try:
        _, history, _ = record_current("Rechazar", "", reason, report, exchanges, state, sectors, selected, *values)
    except gr.Error as exc:
        return warn(exc.message, {decision_status: ""})
    return {**closed_controls(), decision_status: "**Propuesta rechazada. No se guardó nada.**", decision_log: history}


def record_current(decision, order, note, report, exchanges, state, sectors, selected, *values, parts=None, final_report=""):
    try:
        form_values, geometry, settings, scenario = split_edits(values)
        current, current_name = commit_sector(sectors, selected, form_values)
        current = apply_geometry(current, current_name, geometry)
        status, _, trace = human_decision(decision, order, note, state, *analysis_args(current, settings))
        if decision in SAVED_DECISIONS:
            # Un aviso de error de la API no es contenido de la IA: no se guarda como tal.
            kept = [e if not is_unavailable(e["opinion"]) else {**e, "opinion": None} for e in exchanges]
            save_decision(decision_record(decision, order, note, scenario, state, "" if is_unavailable(report) else report, kept, parts,
                                          "" if is_unavailable(final_report) else final_report))
            status += " **Guardada en el historial.**"
        elif decision == "Rechazar":
            status += " **No se guardó ninguna propuesta.**"
        return status, decision_history(), trace
    except (ValueError, TypeError, OSError) as exc:
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
    ia_exchanges = gr.State([])
    ia_report = gr.State("")
    ia_parts = gr.State(None)
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

        with gr.Tab("CLIMA Y SIMULACIÓN", id="clima") as finca_tab:
            gr.Markdown("## Clima y simulación\nCambiá el clima de la finca o la sonda de un sector y mirá cómo responde el suelo. Son datos de prueba, no mediciones de campo.")
            gr.Markdown("### Escenarios rápidos\nCada uno carga sus datos y analiza. Conservan la distribución, los nombres y los canales de los sectores.")
            with gr.Row():
                normal_button = gr.Button("NORMAL")
                zonda_button = gr.Button("ZONDA / ESTRÉS")
                failure_button = gr.Button("FALLA SENSOR")
                canal_button = gr.Button("CANAL DETERIORADO")
            gr.Markdown("### Clima de la finca\nVale para todos los sectores. La lluvia y la ET0 son valores diarios.")
            with gr.Row():
                temp = gr.Number(value=24, minimum=0, maximum=42, label="Temperatura ambiente (°C) · 0–42")
                rh = gr.Number(value=40, minimum=10, maximum=90, label="Humedad relativa (%) · 10–90")
                wind = gr.Number(value=12, minimum=0, maximum=70, label="Viento (km/h) · 0–70")
            with gr.Row():
                rain = gr.Number(value=0, minimum=0, maximum=40, label="Lluvia (mm/día) · 0–40")
                et0 = gr.Number(value=5.5, minimum=1, maximum=12, label="ET0 (mm/día) · 1–12")
            with gr.Row():
                climate_run = gr.Button("ANALIZAR CON ESTE CLIMA", variant="primary")
                reset_button = gr.Button("RESTAURAR ESCENARIO BASE")
            gr.Markdown("### Sonda del sector\nLa sonda mide el efecto del clima sobre el suelo de un sector.")
            with gr.Row():
                sector_selector = gr.Dropdown(NAMES, value=FIRST, label="Sector de la sonda")
                edit_map_button = gr.Button("EDITAR LA FICHA COMPLETA EN EL MAPA")
            with gr.Row():
                with gr.Column(scale=1, min_width=300):
                    sensor_reading = gr.HTML(sensor_detail(INITIAL, FIRST))
                with gr.Column(scale=2, min_width=320):
                    sensor_plot = gr.Plot(value=sensor_twin_figure(INITIAL["history"], FIRST), label="Humedad hora por hora")
            gr.Markdown("Soltá un control y la finca se vuelve a analizar con ese cambio en el sector elegido.")
            with gr.Row():
                lab_connected = gr.Checkbox(value=True, label="Sonda conectada", info="Desconectala para ver cómo trabaja la IA sin medición.")
                lab_humidity = gr.Slider(5, 45, value=float(BASE[7].iloc[0]["humedad_suelo_pct"]), step=0.5, label="Humedad del suelo al empezar (%)", info="Punto de partida de la simulación.")
                hours = gr.Slider(0, 48, value=12, step=1, label="Horas simuladas", info="Tiempo que miden las sondas. Vale para todos los sectores.")
            with gr.Row():
                lab_irrigation = gr.Slider(0, 20, value=0, step=0.5, label="Riego de prueba (mm por hora)", info="Agua hipotética: no riega ni registra nada.")
                lab_noise = gr.Slider(0, 2, value=0.2, step=0.1, label="Imprecisión de la sonda (puntos %)", info="Cuánto varía cada lectura respecto del valor real.")
                lab_button = gr.Button("VOLVER A MEDIR", variant="primary")
            gr.Markdown("### Todos los sectores")
            sector_cards = gr.HTML(sector_cards_html(INITIAL))

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
            gr.Markdown("## IA y decisión\nPrimero leé el informe completo y cómo se llegó a él. Después decidís si estás de acuerdo.")
            with gr.Column(elem_classes="ia-wizard"):
                ia_stepper = gr.HTML(ia_stepper_html(1))
                with gr.Column(elem_classes="ia-step") as ia_step1:
                    with gr.Row():
                        explain_button = gr.Button("CONSULTAR A LA IA", variant="primary")
                        next_button = gr.Button("SIGUIENTE", variant="primary", visible=False)
                    claude_explanation = gr.Markdown("", elem_classes="ai-report")
                    with gr.Column(visible=False) as ia_how:
                        ia_kpis = gr.HTML("")
                        with gr.Tabs(elem_id="report-tabs"):
                            with gr.Tab("Resumen"):
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        rep_summary = gr.Markdown("", elem_classes="report-text")
                                    with gr.Column(min_width=300):
                                        gr.Markdown("#### Datos a revisar")
                                        rep_review = gr.Markdown("", elem_classes="report-text")
                            with gr.Tab("Pérdidas"):
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        ia_loss_bars = gr.HTML("")
                                    with gr.Column(min_width=300):
                                        rep_losses = gr.Markdown("", elem_classes="report-text")
                            with gr.Tab("Reparto del agua"):
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        ia_water_bars = gr.HTML("")
                                    with gr.Column(min_width=300):
                                        rep_water = gr.Markdown("", elem_classes="report-text")
                            with gr.Tab("Reparaciones"):
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        ia_repairs = gr.HTML("")
                                    with gr.Column(min_width=300):
                                        rep_repairs = gr.Markdown("", elem_classes="report-text")
                            with gr.Tab("Cómo llegó"):
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        rep_how = gr.Markdown("", elem_classes="report-text")
                                    with gr.Column(min_width=300):
                                        ia_reasoning = gr.HTML("")
                            with gr.Tab("Modelos") as ia_models_tab:
                                with gr.Row():
                                    with gr.Column(min_width=300):
                                        importance_model = gr.Radio(["Riesgo con sensor", "Riesgo sin sensor", "Pérdidas del canal"], value="Riesgo con sensor", label="Variables que más influyen")
                                        importance_plot = gr.Plot(value=feature_importance_figure(MODELS.sector_with_sensor), label="Importancia global real del modelo")
                                    with gr.Column(min_width=300):
                                        diagnosis_selector = gr.Dropdown(NAMES, value=FIRST, label="Diagnóstico del sector")
                                        ai_explanation = gr.Markdown(ia_detail(INITIAL, FIRST), elem_classes="report-text")
                                with gr.Accordion("Tabla de diagnóstico, métricas y riesgo por sector", open=False):
                                    diagnosis = gr.Dataframe(value=diagnostic_table(INITIAL), interactive=False, label="Diagnóstico por sector", max_height=300)
                                    gr.Markdown(model_description(MODELS))
                                    risk_plot = gr.Plot(value=priority_figure(INITIAL["priority"]), label="Riesgo por sector")
                        gr.Markdown("Redactado por Claude a partir de datos sintéticos. Los números los calcularon los modelos locales. La decisión es del encargado.", elem_classes="report-note")
                with gr.Column(visible=False, elem_classes="ia-step") as ia_step2:
                    with gr.Row():
                        with gr.Column(scale=3, min_width=340):
                            human_recommendation = gr.HTML(water_plan_html(INITIAL))
                            with gr.Column(visible=False) as water_edit_box:
                                water_edit = gr.Dataframe(value=water_edit_table(INITIAL), headers=EDIT_COLUMNS, datatype=["str", "number", "number"], static_columns=[0, 1],
                                                          interactive=True, label="Reparto del agua: editá la columna Tus minutos", max_height=280)
                                water_total = gr.Markdown("")
                            water_choice = gr.Radio([AGREE, WATER_CHANGE], value=None, label="¿Estás de acuerdo con el reparto?")
                            repair_summary = gr.HTML(repair_plan_html(INITIAL))
                            repair_choice = gr.Radio([AGREE, REPAIR_NO], value=None, label="¿Harías esta reparación?")
                        with gr.Column(scale=2, min_width=300):
                            gr.Markdown("### Decidí cada parte\nPodés aceptar una y cambiar la otra. Lo que confirmes se guarda con fecha.")
                            with gr.Column(visible=False) as ia_objection:
                                objection_part = gr.Radio([], value=None, label="Hablar con la IA sobre")
                                ia_thread = gr.Markdown("", elem_classes=["ai-report", "ai-thread"])
                                objection_text = gr.Textbox(lines=2, label="¿Qué no te convence? (opcional)", placeholder="Por ejemplo: el Sector C es olivo y aguanta mejor la sequía")
                                send_objection = gr.Button("PEDIR OPINIÓN A LA IA")
                            decision_status = gr.Markdown("")
                            with gr.Column() as ia_actions:
                                confirm_button = gr.Button(CONFIRM_SAVE, variant="primary")
                                reject_button = gr.Button("RECHAZAR TODO SIN GUARDAR")
                            back_button = gr.Button("VOLVER AL INFORME")
                with gr.Column(visible=False, elem_classes="ia-step") as ia_step3:
                    with gr.Row():
                        with gr.Column(scale=2, min_width=300):
                            ia_comparison = gr.HTML("")
                        with gr.Column(scale=3, min_width=320):
                            gr.Markdown("### Informe final con tus cambios")
                            ia_final_report = gr.Markdown("", elem_classes=["ai-report", "report-final"])
                    decision_final_status = gr.Markdown("")
                    with gr.Row() as ia_final_actions:
                        ia_save_button = gr.Button("GUARDAR EN EL HISTORIAL", variant="primary")
                        edit_button = gr.Button("VOLVER A EDITAR")
                with gr.Accordion("Historial de propuestas guardadas", open=False) as ia_history:
                    decision_log = gr.Dataframe(value=decision_history(), interactive=False, label="Propuestas guardadas", max_height=200)

    form_fields = [sector_name, crop, area, sensor_available, moisture, soil_temp, ec, ndvi, ndvi_age,
                   days, no_irrigation, last_irrigation, restriction, noise, irrigation]
    geometry_fields = [map_x, map_y, map_width, map_height, map_channel]
    global_fields = [temp, rh, wind, rain, et0, flow, turn_hours, channels, hours]
    lab_fields = [lab_connected, lab_humidity, lab_irrigation, lab_noise]
    edit_inputs = [sectors_state, sector_selector] + form_fields + geometry_fields + global_fields + [scenario_state]
    all_outputs = [sectors_state, result_state, scenario_state, sector_selector, diagnosis_selector,
                   summary_cards, diagnosis, sensor_plot, sensor_reading,
                   ai_explanation, risk_plot, audit_table, water_path, status, decision_status, decision_log, add_button, remove_button, map_selector, farm_canvas, summary_map, map_detail, map_notice,
                   current_recommendation, human_recommendation, sector_cards, operation_info, claude_explanation,
                   ia_stepper, ia_step1, ia_step2, ia_step3, ia_how, next_button, ia_report, explain_button, ia_exchanges, ia_parts, water_choice, repair_choice, water_edit_box,
                   repair_summary, ia_actions, ia_objection, objection_part, confirm_button, ia_final_actions, ia_final_report, decision_final_status, ia_thread, objection_text] + form_fields + geometry_fields + global_fields + lab_fields
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
    for trigger in [lab_connected.input, lab_button.click] + [slider.release for slider in lab_fields[1:] + [hours]]:
        trigger(sensor_lab, inputs=edit_inputs + lab_fields, outputs=all_outputs, api_name=False, concurrency_id="dashboard", concurrency_limit=1)
    for field in form_fields + global_fields:
        if field is not sensor_available and field is not hours:  # Las horas analizan al soltar el control.
            field.input(invalidate, inputs=[sectors_state, channels, sector_selector], outputs=all_outputs, queue=False, api_name=False)
    for field in geometry_fields:
        field.input(preview_geometry, inputs=[sectors_state, sector_selector, channels, result_state] + geometry_fields,
                    outputs=all_outputs, api_name=False, concurrency_id="dashboard")
    sensor_available.input(toggle_sensor, inputs=[sensor_available, sectors_state, channels, sector_selector], outputs=all_outputs, queue=False, api_name=False)
    for selector in [sector_selector, map_selector]:
        selector.input(select_sector, inputs=[selector, sectors_state, result_state, channels], outputs=all_outputs, api_name="seleccionar_sector" if selector is map_selector else False)
    diagnosis_selector.input(ia_detail, inputs=[result_state, diagnosis_selector], outputs=ai_explanation, api_name=False)
    importance_model.change(importance_for, inputs=importance_model, outputs=importance_plot, api_name="importancia")
    for tab, kind, plot in [(finca_tab, "sensor", sensor_plot), (ia_models_tab, "importance", importance_plot)]:
        tab.select(partial(refresh_plot, kind), inputs=[result_state, sector_selector, importance_model, plot_revision], outputs=[plot, plot_revision], api_name=False)
    for button in [view_map_button, edit_map_button]:
        button.click(lambda: gr.update(selected="mapa"), outputs=workspace_tabs, api_name=False)
    consult_outputs = [claude_explanation, explain_button, ia_how, next_button, ia_report, rep_summary, rep_review, rep_losses, rep_water,
                       rep_repairs, rep_how, ia_kpis, ia_loss_bars, ia_water_bars, ia_repairs, ia_reasoning, water_edit, water_total]
    explain_button.click(start_consult, outputs=consult_outputs, api_name=False).then(
        consult_ia, inputs=[result_state, scenario_state, turn_hours], outputs=consult_outputs, api_name="explicar_ia")
    ia_models_tab.select(lambda result: priority_figure(result["priority"]) if result else None, inputs=result_state, outputs=risk_plot, api_name=False)
    step_outputs, to_top = [ia_stepper, ia_step1, ia_step2, ia_step3], "() => document.querySelector('.ia-wizard')?.scrollIntoView({behavior: 'smooth', block: 'start'})"
    # El desplazamiento va en un paso aparte: combinado con la función de Python rompe el envío del evento.
    next_button.click(partial(go_to_step, 2), outputs=step_outputs, api_name=False).then(None, js=to_top)
    back_button.click(partial(go_to_step, 1), outputs=step_outputs, api_name=False).then(None, js=to_top)
    edit_button.click(partial(go_to_step, 2), outputs=step_outputs, api_name=False).then(None, js=to_top)
    parts_outputs = [water_edit_box, human_recommendation, ia_objection, objection_part, confirm_button]
    for radio in [water_choice, repair_choice]:
        radio.input(on_parts_change, inputs=[water_choice, repair_choice], outputs=parts_outputs, api_name=False, queue=False)
    water_edit.change(water_total_text, inputs=[water_edit, turn_hours], outputs=water_total, api_name=False, queue=False)
    opinion_outputs = [send_objection, ia_exchanges, ia_thread, objection_text]
    send_objection.click(start_opinion, outputs=opinion_outputs, api_name=False).then(
        ask_opinion, inputs=[objection_part, objection_text, water_edit, ia_report, ia_exchanges, result_state, scenario_state], outputs=opinion_outputs, api_name="opinion_ia")
    context_inputs = [ia_report, ia_exchanges, result_state] + edit_inputs
    closing_outputs = [ia_actions, ia_objection, water_edit_box, human_recommendation, water_choice, repair_choice, decision_log, ia_history]
    confirm_outputs = closing_outputs + step_outputs + [decision_status, ia_parts, ia_comparison, decision_final_status, ia_final_report, ia_final_actions, confirm_button]
    # El tercer paso restaura el texto del botón según lo que el usuario haya elegido.
    confirm_button.click(start_confirm, outputs=confirm_button, api_name=False).then(
        confirm_parts, inputs=[water_choice, repair_choice, water_edit] + context_inputs, outputs=confirm_outputs, api_name="decision_humana").then(
        on_parts_change, inputs=[water_choice, repair_choice], outputs=parts_outputs, api_name=False).then(None, js=to_top)
    ia_save_button.click(save_parts, inputs=[ia_parts, ia_final_report] + context_inputs, outputs=closing_outputs + [decision_final_status, ia_final_actions], api_name=False)
    reject_button.click(reject_all, inputs=context_inputs, outputs=closing_outputs + [decision_status], api_name=False)
    gr.Markdown("Etapa 1 · Lozano → Siccardi → Sosa → Rivamar. Uso de IA: ChatGPT como apoyo; el equipo debe verificar supuestos y decisiones antes de entregar.")

if __name__ == "__main__":
    demo.launch(inbrowser=True, server_name="127.0.0.1", share=False,
                theme=gr.themes.Default(primary_hue="emerald", secondary_hue="sky", neutral_hue="slate",
                                        font_mono=["Source Sans Pro", "Arial", "sans-serif"]).set(
                    button_primary_background_fill="#216c50", button_primary_background_fill_hover="#19543e",
                    button_primary_background_fill_dark="#235e44", button_primary_text_color="#ffffff",
                    block_label_text_color="#536961", block_label_text_color_dark="#a8b9b0"),
                css=CSS_PATH.read_text())
