"""Presentación del MVP: datos resumidos, diagramas y gráficos. Sin decisiones de riego."""
from __future__ import annotations

import html
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def esc(value):
    return html.escape(str(value))


def chart_layout(fig, title, height=330):
    fig.update_layout(template="plotly_white", title=dict(text=title, font=dict(size=16)),
                      height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial, sans-serif", size=12, color="#50616c"),
                      margin=dict(l=52, r=24, t=52, b=48), showlegend=False)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(127,145,153,0.16)", zeroline=False)
    return fig


def sensor_twin_figure(history, selected=None):
    fig = go.Figure()
    if history is not None and len(history):
        rows = history if selected is None else history[history["sector"] == selected]
        for sector, readings in rows.groupby("sector", sort=False):
            if readings["humedad_suelo_pct"].notna().any():
                fig.add_scatter(x=readings["hora"], y=readings["humedad_suelo_pct"], mode="lines+markers",
                                name=sector, line=dict(width=3.5, color="#14506f", shape="spline"), marker=dict(size=6), fill="tozeroy", fillcolor="rgba(20,80,111,0.12)",
                                hovertemplate="Hora %{x}<br>Humedad %{y:.2f}%<extra>" + esc(sector) + "</extra>")
    title = "Evolución de humedad" + (f" · {esc(selected)}" if selected else "")
    chart_layout(fig, title)
    fig.update_xaxes(title="Tiempo simulado (h)", dtick=2)
    fig.update_yaxes(title="Humedad del suelo (%)", range=[5, 45])
    if fig.data:
        # Mismo umbral que usa el sensor virtual para pasar a ADVERTENCIA.
        fig.add_hline(y=18, line_dash="dot", line_color="#8f2622", line_width=1.5,
                      annotation_text="Bajo 18%: advertencia", annotation_position="bottom right", annotation_font_color="#8f2622")
    if not fig.data:
        fig.add_annotation(text="Sin medición disponible. La IA puede estimar riesgo, no humedad.",
                           x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return fig


def priority_figure(priority):
    colors = ["#b3413e" if v >= 70 else "#a47516" if v >= 45 else "#237958"
              for v in priority["riesgo_deficit_ia_0_100"].fillna(-1)]
    fig = go.Figure(go.Bar(x=priority["sector"], y=priority["riesgo_deficit_ia_0_100"], marker_color=colors))
    chart_layout(fig, "Riesgo hídrico estimado por sector")
    fig.update_yaxes(title="Riesgo IA (0–100)", range=[0, 100])
    return fig


def feature_importance_figure(model):
    values = pd.Series(model.feature_importances_ * 100, index=model.feature_names_in_).sort_values()
    fig = go.Figure(go.Bar(x=values.values, y=values.index, orientation="h", marker_color="#2875a0"))
    chart_layout(fig, "Variables que más influyen en la predicción", 370)
    fig.update_layout(margin=dict(l=192, r=24, t=52, b=48))
    fig.update_xaxes(title="Importancia global del Random Forest (%)")
    return fig


def metric_card(label, value, detail="", tone="info"):
    return f'<article class="stat-card {tone}"><div class="stat-label">{esc(label)}</div><div class="stat-value">{esc(value)}</div><div class="stat-detail">{esc(detail)}</div></article>'


def summary_html(result, scenario, sectors):
    cards = [metric_card("Finca", f"{len(sectors)} sectores", "Croquis editable · 1–10 sectores", "neutral")]
    if result is None:
        for label in ["Sector crítico", "Riesgo máximo", "Canal crítico", "Pérdida", "Reparación recomendada"]:
            cards.append(metric_card(label, "Pendiente", "Analizá la finca", "neutral"))
    else:
        valid = result["priority"].dropna(subset=["riesgo_deficit_ia_0_100"])
        if len(valid):
            critical = valid.loc[valid["riesgo_deficit_ia_0_100"].idxmax()]
            risk = critical["riesgo_deficit_ia_0_100"]
            tone = "critical" if risk >= 70 else "warning" if risk >= 45 else "normal"
            cards.extend([metric_card("Sector crítico", critical["sector"], critical["estado"], tone),
                          metric_card("Riesgo máximo", f"{risk:.1f} / 100", "Predicción Random Forest", tone)])
        else:
            cards.extend([metric_card("Sector crítico", "Sin datos", "Revisión humana", "neutral"),
                          metric_card("Riesgo máximo", "No disponible", "Sin entradas suficientes", "neutral")])
        audit = result["audit"]
        worst, repair = audit.loc[audit["perdida_ia_pct"].idxmax()], audit.iloc[0]
        cards.extend([metric_card("Canal crítico", worst["tramo"], "Mayor pérdida porcentual", "warning"),
                      metric_card("Pérdida", f"{worst['perdida_ia_pct']:.2f}%", "Estimación IA del canal crítico", "warning"),
                      metric_card("Reparación recomendada", repair["tramo"], "Mejor relación agua / costo")])
    return '<div class="stat-grid">' + ''.join(cards) + '</div>'


def operational_info(result):
    if result is None:
        return "Eficiencia y lecturas pendientes de análisis."
    route = result["audit"].sort_values("orden_recorrido")
    efficiency = route.iloc[-1]["agua_salida_l"] / route.iloc[0]["agua_entrada_l"] * 100
    active = result["sectors"]["humedad_suelo_pct"].notna().sum()
    return f"**Eficiencia calculada:** {efficiency:.1f}% (salida / entrada). **Sensores virtuales con lectura:** {active}/{len(result['sectors'])}."


def sector_cards_html(result):
    if result is None:
        return '<p class="empty-note">Analizá la finca para actualizar las tarjetas.</p>'
    risks = result["priority"].set_index("sector")
    cards = []
    for _, row in result["sectors"].iterrows():
        risk = risks.loc[row["sector"]]
        humidity = f"{row['humedad_suelo_pct']:.1f}%" if pd.notna(row["humedad_suelo_pct"]) else "NO DISPONIBLE"
        score = f"{risk['riesgo_deficit_ia_0_100']:.1f}/100" if pd.notna(risk["riesgo_deficit_ia_0_100"]) else "Sin predicción"
        cards.append(f'<article class="sector-mini"><h3>{esc(row["sector"])}</h3><p>{esc(row["cultivo"])}</p><p>Humedad: <strong>{humidity}</strong></p><p>Riesgo IA: <strong>{score}</strong></p><small>{esc(risk["estado"])}</small></article>')
    return '<div class="sector-card-grid">' + ''.join(cards) + '</div>'


def repair_view(result):
    df = result["audit"][["prioridad_reparacion", "tramo", "perdida_ia_pct", "agua_perdida_l", "litros_recuperables_si_repara", "costo_reparacion_ars", "l_recuperables_por_1000_ars"]].copy()
    df.columns = ["Prioridad", "Tramo", "Pérdida IA (%)", "Litros perdidos", "Litros recuperables", "Costo (ARS)", "Litros / $1000"]
    return df


def diagnostic_table(result):
    if result is None:
        return pd.DataFrame(columns=["Sector", "Riesgo IA /100", "Estado", "Confianza", "Motivo"])
    p = result["priority"]
    df = p[["sector", "riesgo_deficit_ia_0_100", "estado", "confianza", "evidencia"]].copy()
    df.columns = ["Sector", "Riesgo IA /100", "Estado", "Confianza", "Motivo"]
    return df


SENSOR_STATES = {"NORMAL": ("ok", "Midiendo con normalidad"), "ADVERTENCIA": ("warn", "Atención: revisar esta lectura"),
                 "SIN SENSOR": ("off", "Sonda desconectada"), "LECTURA ANÓMALA": ("bad", "Lectura descartada por estar fuera de rango")}


def _scale(value, low, high):
    return round(max(0.0, min(100.0, (float(value) - low) / (high - low) * 100)), 1)


def _probe_tile(label, value, unit, low, high, fmt):
    if pd.isna(value):
        return f'<div class="probe-tile is-empty"><span>{label}</span><b>NO DISPONIBLE</b><small>La sonda no entrega este dato</small></div>'
    return (f'<div class="probe-tile"><span>{label}</span><b>{fmt.format(value)}<em>{unit}</em></b>'
            f'<div class="probe-scale"><i style="width:{_scale(value, low, high)}%"></i></div><small>La sonda mide de {low} a {high} {unit}</small></div>')


def _probe_art(humidity, tone):
    measured = pd.notna(humidity)
    water = _scale(humidity, 5, 45) if measured else 0
    mark = f'<text x="104" y="{max(80, 166 - water)}" text-anchor="end" font-size="9" font-weight="700" class="probe-mark">{humidity:.0f}%</text>' if measured else ''
    return (f'<svg viewBox="0 0 120 180" class="probe-art{"" if measured else " is-off"}" role="img" aria-label="Sonda clavada en el suelo; el azul muestra la humedad medida">'
            '<clipPath id="probe-soil-clip"><rect x="10" y="70" width="100" height="100" rx="12"/></clipPath>'
            '<rect x="10" y="70" width="100" height="100" rx="12" class="probe-soil"/>'
            f'<rect x="10" y="{170 - water}" width="100" height="{water}" class="probe-water" clip-path="url(#probe-soil-clip)"/>'
            '<path d="M2 70 H118" class="probe-ground"/>'
            '<rect x="55" y="50" width="10" height="94" rx="2" class="probe-stake"/><path d="M55 144 L60 157 L65 144 Z" class="probe-stake"/>'
            '<path d="M57 86 H63 M57 104 H63 M57 122 H63" class="probe-rings"/>'
            '<rect x="41" y="14" width="38" height="40" rx="9" class="probe-head"/>'
            f'<circle cx="60" cy="30" r="5.5" class="probe-led led-{tone}"/>'
            '<path d="M50 44 H70" class="probe-rings"/>' + mark + '</svg>')


def sensor_detail(result, selected):
    if result is None:
        return '<div class="sensor-note">Analizá la finca para ver qué mide la sonda.</div>'
    row = result["sectors"].set_index("sector").loc[selected]
    risk = result["priority"].set_index("sector").loc[selected]
    state = row["estado_sensor"]
    tone, status = SENSOR_STATES.get(state, ("off", state))
    humidity = row["humedad_suelo_pct"]
    if state == "ADVERTENCIA" and pd.notna(humidity) and humidity < 18:
        status = "Atención: humedad baja, menos de 18%"
    readings = result["history"].loc[result["history"]["sector"] == selected, "humedad_suelo_pct"].dropna()
    if len(readings) > 1:
        change, hours = readings.iloc[-1] - readings.iloc[0], len(readings) - 1
        trend = (f"La humedad {'bajó' if change < 0 else 'subió'} {abs(change):.1f} puntos en {hours} h simuladas."
                 if abs(change) >= 0.05 else f"La humedad se mantuvo estable en {hours} h simuladas.")
    elif len(readings) == 1:
        trend = "Lectura inicial: todavía no pasó tiempo simulado."
    else:
        trend = "Sin lecturas: la curva no se dibuja porque no hay medición."
    score = risk["riesgo_deficit_ia_0_100"]
    if pd.isna(score):
        ai = "Faltan datos para que la IA estime el riesgo de este sector."
    elif pd.isna(humidity):
        ai = f"Sin medición de humedad, la IA estima el riesgo con clima e historial: {score:.1f}/100. Confianza {risk['confianza']}."
    else:
        ai = f"Con esta lectura, la IA estima un riesgo de {score:.1f}/100. Confianza {risk['confianza']}."
    tiles = (_probe_tile("Humedad del suelo", humidity, "%", 5, 45, "{:.1f}")
             + _probe_tile("Temperatura del suelo", row["temperatura_suelo_c"], "°C", 5, 35, "{:.1f}")
             + _probe_tile("Salinidad (EC)", row["ec_ds_m"], "dS/m", 0.2, 4.5, "{:.2f}"))
    return (f'<section class="probe-card"><header><h3>Sonda de {esc(selected)}</h3>'
            f'<p class="probe-status tone-{tone}"><i class="led-{tone}"></i>{esc(status)}</p></header>'
            f'<div class="probe-body">{_probe_art(humidity, tone)}<div class="probe-tiles">{tiles}</div></div>'
            f'<p class="probe-trend">{esc(trend)}</p><p class="probe-ai">{esc(ai)} {esc(risk["estado"]).capitalize()}.</p>'
            '<small>Sensor virtual: datos de prueba, no es una medición de campo.</small></section>')


def ia_detail(result, selected):
    if result is None:
        return "Ejecutá la simulación para ver qué entradas utilizó la IA."
    row = result["priority"].set_index("sector").loc[selected]
    value = f"{row['riesgo_deficit_ia_0_100']:.1f}/100" if pd.notna(row["riesgo_deficit_ia_0_100"]) else "NO DISPONIBLE"
    return (f"### {esc(selected)} · riesgo {value}\n\n**Modelo:** RandomForestRegressor · {esc(row['modo'])}. "
            f"**Confianza por calidad de datos:** {row['confianza']}.\n\n{esc(row['evidencia'])}.\n\n"
            f"**Humedad directa:** {esc(row['humedad_directa'])}.\n\n**Recomendación:** {esc(row['accion_sugerida'])}. "
            f"{esc(row['advertencias']).rstrip('.')}.")


def _miles(value):
    return f"{value:,.0f}".replace(",", ".")


def water_plan_html(result):
    if result is None:
        return '<p class="empty-note">Analizá la finca para ver la propuesta.</p>'
    items = []
    for _, row in result["priority"].iterrows():
        risk = row["riesgo_deficit_ia_0_100"]
        detail = f"Riesgo {risk:.1f}/100, confianza {esc(row['confianza'])}" if pd.notna(risk) else "Sin predicción por falta de datos"
        minutes = f"{row['tiempo_sugerido_min']:.0f} min" if row["tiempo_sugerido_min"] > 0 else "Revisar antes de regar"
        items.append(f'<li><b>{esc(row["sector"])}</b><span>{detail}</span><strong>{minutes}</strong></li>')
    return '<section class="plan-card"><h4>Reparto del agua propuesto</h4><ol class="plan-list">' + "".join(items) + "</ol></section>"


def repair_plan_html(result, significant_loss=20):
    """20% es el umbral que pinta un tramo en rojo en el mapa."""
    if result is None:
        return ""
    audit = result["audit"].sort_values("orden_recorrido")
    high = audit[audit["perdida_ia_pct"] >= significant_loss]
    losses = (f"Tramos con pérdida de {significant_loss}% o más: " + ", ".join(
        f"{esc(r['tramo'])} ({r['perdida_ia_pct']:.1f}%, {_miles(r['agua_perdida_l'])} L)" for _, r in high.iterrows()) + "."
        if len(high) else f"Ningún tramo llega al {significant_loss}% de pérdida.")
    repair = result["audit"].iloc[0]
    return (f'<section class="plan-card"><h4>Reparación sugerida</h4><p><b>{esc(repair["tramo"])}</b>: cuesta ${_miles(repair["costo_reparacion_ars"])} ARS y recuperaría unos '
            f'{_miles(repair["litros_recuperables_si_repara"])} L por turno, suponiendo que reparar recupera el 70% de la pérdida.</p><p class="plan-losses">{losses}</p></section>')


def parts_comparison_html(parts):
    water, repair = parts["reparto"], parts["reparacion"]
    final = {r["sector"]: r["minutos"] for r in water["final"]}
    rows = "".join(f'<tr{" class=changed" if abs(final[r["sector"]] - r["minutos"]) >= .05 else ""}><td>{esc(r["sector"])}</td><td>{r["minutos"]:.0f}</td><td>{final[r["sector"]]:.0f}</td></tr>'
                   for r in water["original"])
    water_state = "Lo cambiaste" if water["decision"] == "cambiado" else "De acuerdo"
    repair_state = "La rechazaste" if repair["decision"] == "rechazada" else "De acuerdo"
    reason = lambda part: f'<p class="why">Motivo: {esc(part["motivo"])}</p>' if part["motivo"] else ""
    return (f'<section class="plan-card"><h4>Reparto del agua: {water_state}</h4><table class="how-table compare"><thead><tr><th>Sector</th><th>Propuesto</th><th>Final</th></tr></thead><tbody>{rows}</tbody></table>{reason(water)}'
            f'<h4>Reparación de {esc(repair["tramo"])}: {repair_state}</h4><p>${_miles(repair["costo_ars"])} ARS, recuperaría unos {_miles(repair["litros_recuperables"])} L.</p>{reason(repair)}</section>')


def ia_stepper_html(step):
    names = ["Informe de la IA", "Tu decisión", "Confirmar"]
    items = "".join(f'<li{" aria-current=step" if i == step else ""}{" class=done" if i < step else ""}><b>{i}</b>{name}</li>'
                    for i, name in enumerate(names, 1))
    return f'<ol class="ia-steps">{items}</ol>'


def _cell(value, fmt):
    return fmt.format(value) if pd.notna(value) else "Sin dato"


def reasoning_html(result):
    """Los cálculos reales detrás del informe, tomados del análisis y no redactados por el modelo de lenguaje."""
    if result is None:
        return ""
    priority, route = result["priority"], result["audit"].sort_values("orden_recorrido")
    measured = int(result["sectors"]["humedad_suelo_pct"].notna().sum())
    sector_rows = "".join(
        f'<tr><td>{r["orden_propuesto"]}</td><td>{esc(r["sector"])}</td><td>{esc(r["modo"])}</td><td>{_cell(r["riesgo_deficit_ia_0_100"], "{:.1f}")}</td>'
        f'<td>{esc(r["confianza"])}</td><td>{_cell(r["puntaje_prioridad"], "{:.1f}")}</td><td>{r["tiempo_sugerido_min"]:.1f}</td></tr>'
        for _, r in priority.iterrows())
    channel_rows = "".join(
        f'<tr><td>{esc(r["tramo"])}</td><td>{r["perdida_ia_pct"]:.2f}%</td><td>{_miles(r["agua_perdida_l"])}</td><td>{_miles(r["litros_recuperables_si_repara"])}</td>'
        f'<td>${_miles(r["costo_reparacion_ars"])}</td><td>{r["l_recuperables_por_1000_ars"]:.2f}</td><td>{r["prioridad_reparacion"]}</td></tr>'
        for _, r in route.iterrows())
    return ('<div class="how-block"><ol class="how-steps">'
            f'<li><b>Lecturas.</b> La sonda virtual entregó lectura en {measured} de {len(result["sectors"])} sectores.</li>'
            '<li><b>Riesgo.</b> Un Random Forest estimó el riesgo de cada sector con clima, NDVI, historial y la lectura de la sonda. Sin lectura, usó otro modelo que no toca humedad.</li>'
            f'<li><b>Prioridad.</b> Regla fija: {esc(priority.iloc[0]["regla_prioridad"])}. Los minutos del turno se reparten según puntaje y superficie.</li>'
            '<li><b>Canales.</b> Otro Random Forest estimó la pérdida de cada tramo. Los litros se calculan tramo a tramo y la reparación se ordena por litros recuperables cada $1000.</li>'
            '<li><b>Informe.</b> Claude redactó el texto con estos resultados. No calculó ninguna cifra.</li></ol>'
            '<h4>Sectores</h4><div class="how-scroll"><table class="how-table"><thead><tr><th>Orden</th><th>Sector</th><th>Modelo</th><th>Riesgo /100</th><th>Confianza</th><th>Puntaje</th><th>Minutos</th></tr></thead>'
            f'<tbody>{sector_rows}</tbody></table></div>'
            '<h4>Canales, en orden de recorrido</h4><div class="how-scroll"><table class="how-table"><thead><tr><th>Tramo</th><th>Pérdida</th><th>Litros perdidos</th><th>Litros recuperables</th><th>Costo</th><th>Litros / $1000</th><th>Prioridad</th></tr></thead>'
            f'<tbody>{channel_rows}</tbody></table></div></div>')


def report_kpis_html(result, significant_loss=20):
    route = result["audit"].sort_values("orden_recorrido")
    water_in, water_out = route.iloc[0]["agua_entrada_l"], route.iloc[-1]["agua_salida_l"]
    over = int((route["perdida_ia_pct"] >= significant_loss).sum())
    first, repair = result["priority"].iloc[0], result["audit"].iloc[0]
    tiles = [("Llega al final", f"{water_out / water_in * 100:.1f}%", f"de {_miles(water_in)} L", "info"),
             ("Agua perdida", f"{_miles(water_in - water_out)} L", "en todo el recorrido", "critical"),
             (f"Tramos sobre {significant_loss}%", f"{over} de {len(route)}", "pérdida significativa", "warning" if over else "normal"),
             ("Regar primero", first["sector"], f"{first['tiempo_sugerido_min']:.0f} min sugeridos", "info"),
             ("Reparar primero", repair["tramo"], f"${_miles(repair['costo_reparacion_ars'])} ARS", "info")]
    return '<div class="kpi-strip">' + "".join(
        f'<div class="kpi {tone}"><span>{esc(label)}</span><b>{esc(value)}</b><small>{esc(detail)}</small></div>' for label, value, detail, tone in tiles) + "</div>"


def _bar(label, width, value, tone, marker=None):
    tick = f'<u style="left:{marker:.1f}%"></u>' if marker is not None else ""
    return (f'<div class="bar-row"><span>{esc(label)}</span><div class="bar-track"><i class="{tone}" style="width:{min(width, 100):.1f}%"></i>{tick}</div>'
            f"<b>{esc(value)}</b></div>")


def loss_bars_html(result, significant_loss=20):
    route = result["audit"].sort_values("orden_recorrido")
    top = max(30.0, float(route["perdida_ia_pct"].max()) * 1.1)
    bars = "".join(_bar(r["tramo"], r["perdida_ia_pct"] / top * 100, f'{r["perdida_ia_pct"]:.1f}%',
                        "high" if r["perdida_ia_pct"] >= significant_loss else "medium" if r["perdida_ia_pct"] >= 10 else "low",
                        significant_loss / top * 100) for _, r in route.iterrows())
    return f'<div class="bars"><h4>Pérdida por tramo</h4>{bars}<small>La marca vertical es el umbral de {significant_loss}%.</small></div>'


def water_bars_html(result):
    priority = result["priority"]
    top = max(float(priority["tiempo_sugerido_min"].max()), 1.0)
    bars = "".join(_bar(r["sector"], r["tiempo_sugerido_min"] / top * 100, f'{r["tiempo_sugerido_min"]:.0f} min' if r["tiempo_sugerido_min"] > 0 else "Revisar", "water")
                   for _, r in priority.iterrows())
    return f'<div class="bars"><h4>Minutos del turno por sector</h4>{bars}<small>En el orden propuesto.</small></div>'


def repair_cards_html(result, significant_loss=20):
    cards = "".join(
        f'<article class="repair{" is-first" if i == 0 else ""}"><b>{esc(r["tramo"])}</b><span>${_miles(r["costo_reparacion_ars"])} ARS</span>'
        f'<span>Recupera {_miles(r["litros_recuperables_si_repara"])} L</span><span>{r["l_recuperables_por_1000_ars"]:.0f} L cada $1000</span>'
        + (f'<em>Pierde {r["perdida_ia_pct"]:.1f}%</em>' if r["perdida_ia_pct"] >= significant_loss else "") + "</article>"
        for i, (_, r) in enumerate(result["audit"].iterrows()))
    return f'<div class="repairs"><h4>Reparaciones, de mejor a peor rendimiento</h4><div class="repair-grid">{cards}</div></div>'


def water_route(audit):
    if audit is None or not len(audit):
        return '<p class="empty-note">Simulá para ver el recorrido del agua.</p>'
    route = audit.sort_values("orden_recorrido")
    blocks = [f'<div class="water-stop"><strong>ENTRADA</strong><b>{route.iloc[0]["caudal_entrada_ls"]:.2f} L/s</b></div>']
    for _, row in route.iterrows():
        blocks.append(f'<div class="water-stop"><strong>{esc(row["tramo"])}</strong><b>{row["caudal_salida_ls"]:.2f} L/s</b><span>Sale · pérdida IA {row["perdida_ia_pct"]:.2f}%</span><small>Entra {row["caudal_entrada_ls"]:.2f} L/s</small></div>')
    blocks.append(f'<div class="water-stop"><strong>SALIDA</strong><b>{route.iloc[-1]["caudal_salida_ls"]:.2f} L/s</b></div>')
    return '<div class="water-route">' + '<span class="flow-arrow" aria-hidden="true">→</span>'.join(blocks) + '</div>'


def model_description(models):
    lines = ["**RandomForestRegressor · 160 árboles · semilla fija · 80% entrenamiento / 20% prueba.**"]
    for key, label, model in [("sector_sensor", "Riesgo con sensor", models.sector_with_sensor),
                              ("sector_proxy", "Riesgo sin sensor", models.sector_proxy),
                              ("canal", "Pérdidas del canal", models.channel_loss)]:
        m = models.metrics[key]
        lines.append(f"**{label}:** MAE {m['mae']:.2f} · R² {m['r2']:.3f} · {m['n_total']} ejemplos sintéticos "
                     f"({m['n_train']} entrenamiento / {m['n_test']} prueba).\n\nEntradas: `{', '.join(model.feature_names_in_)}`.")
    lines.append("**Las métricas corresponden al dataset sintético y no representan precisión validada en campo.** "
                 "La importancia es global y la confianza es una regla de calidad, no una probabilidad estadística.")
    return '\n\n'.join(lines)
