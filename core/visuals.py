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
                                name=sector, line=dict(width=3, color="#2875a0"), marker=dict(size=5),
                                hovertemplate="Hora %{x}<br>Humedad %{y:.2f}%<extra>" + esc(sector) + "</extra>")
    title = "Evolución de humedad" + (f" · {esc(selected)}" if selected else "")
    chart_layout(fig, title)
    fig.update_xaxes(title="Tiempo simulado (h)", dtick=2)
    fig.update_yaxes(title="Humedad del suelo (%)", range=[5, 45])
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


def compact_sectors(sectors):
    df = sectors[["sector", "cultivo", "sensor_disponible", "humedad_suelo_pct", "ndvi"]].copy()
    df["sensor_disponible"] = df["sensor_disponible"].map({1: "Disponible", 0: "Sin sensor"})
    df["humedad_suelo_pct"] = [f"{v:.1f}%" if pd.notna(v) else "No disponible" for v in df["humedad_suelo_pct"]]
    df.columns = ["Sector", "Cultivo", "Sensor virtual", "Humedad inicial", "NDVI simulado"]
    return df


def proposal_view(result):
    df = result["priority"][["orden_propuesto", "sector", "riesgo_deficit_ia_0_100", "confianza", "tiempo_sugerido_min"]].copy()
    df.columns = ["Orden", "Sector", "Riesgo IA /100", "Confianza", "Tiempo sugerido (min)"]
    return df


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


def sensor_detail(result, selected):
    if result is None:
        return '<div class="sensor-note">Ejecutá la simulación para ver la lectura final.</div>'
    row = result["sectors"].set_index("sector").loc[selected]
    risk = result["priority"].set_index("sector").loc[selected]
    humidity = f"{row['humedad_suelo_pct']:.2f}%" if pd.notna(row["humedad_suelo_pct"]) else "NO DISPONIBLE"
    temperature = f"{row['temperatura_suelo_c']:.1f} °C" if pd.notna(row["temperatura_suelo_c"]) else "No disponible"
    ec = f"{row['ec_ds_m']:.2f} dS/m" if pd.notna(row["ec_ds_m"]) else "No disponible"
    extra = "Sin sensor físico no existe una medición directa de humedad. Riesgo estimado con proxies." if pd.isna(row["humedad_suelo_pct"]) else "Última lectura del horizonte simulado; no es una medición de campo."
    return f'<div class="sensor-note"><strong>{esc(row["estado_sensor"])}</strong><div class="sensor-values"><span>Humedad <b>{humidity}</b></span><span>Suelo <b>{temperature}</b></span><span>EC <b>{ec}</b></span></div><p>{esc(extra)} Confianza: {esc(risk["confianza"])}.</p><small>SENSOR VIRTUAL / DATO DE PRUEBA</small></div>'


def ia_detail(result, selected):
    if result is None:
        return "Ejecutá la simulación para ver qué entradas utilizó la IA."
    row = result["priority"].set_index("sector").loc[selected]
    value = f"{row['riesgo_deficit_ia_0_100']:.1f}/100" if pd.notna(row["riesgo_deficit_ia_0_100"]) else "NO DISPONIBLE"
    return (f"### {esc(selected)} · riesgo {value}\n\n**Modelo:** RandomForestRegressor · {esc(row['modo'])}. "
            f"**Confianza por calidad de datos:** {row['confianza']}.\n\n{esc(row['evidencia'])}.\n\n"
            f"**Humedad directa:** {esc(row['humedad_directa'])}.\n\n**Recomendación:** {esc(row['accion_sugerida'])}. "
            f"{esc(row['advertencias']).rstrip('.')}.")


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


def architecture_html():
    def pipeline(labels):
        return '<div class="architecture-flow">' + ''.join(f'<div class="architecture-node">{esc(label)}</div>' + ('<span aria-hidden="true">↓</span>' if i < len(labels) - 1 else '') for i, label in enumerate(labels)) + '</div>'
    return '<div class="architecture-grid"><section><h3>Recomendación de riego</h3>' + pipeline([
        "Finca", "Sectores + clima", "Sensores virtuales", "Agente de Datos", "Modelo IA · riesgo", "Diagnóstico", "Priorización · reglas", "Recomendación → humano"]) + '</section><section><h3>Auditor de canales</h3>' + pipeline([
        "Canal", "IA · pérdidas", "Cálculo · litros perdidos", "Análisis de reparación", "Recomendación → humano"]) + '</section></div>'
