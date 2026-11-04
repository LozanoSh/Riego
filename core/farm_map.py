"""SVG de un croquis relativo: visualiza resultados existentes, no realiza hidráulica ni GIS."""
from __future__ import annotations

from html import escape
import pandas as pd

from .farm import channel_registry

SECTOR_COLORS = {"low": ("#e7f3e9", "#216c50"), "medium": ("#fff3d0", "#875c0b"),
                 "high": ("#fde8e6", "#a73732"), "unknown": ("#edf0ee", "#65716e")}
CHANNEL_COLORS = {"low": "#2875a0", "medium": "#a47516", "high": "#b3413e", "unknown": "#65716e"}


def safe(value):
    return escape(str(value), quote=True)


def sector_state(row):
    if row is None or pd.isna(row.get("riesgo_deficit_ia_0_100")) or row.get("confianza") == "BAJA":
        return "unknown"
    risk = float(row["riesgo_deficit_ia_0_100"])
    return "high" if risk >= 70 else "medium" if risk >= 45 else "low"


def channel_state(loss):
    if loss is None or pd.isna(loss):
        return "unknown"
    return "high" if loss >= 20 else "medium" if loss >= 10 else "low"


def result_lookups(result):
    if result is None:
        return {}, {}, {}
    return (result["priority"].set_index("sector").to_dict("index"),
            result["sectors"].set_index("sector").to_dict("index"),
            result["audit"].set_index("canal_id").to_dict("index"))


def farm_map_html(sectors, channels, result, selected=None, preview=False, canvas_id="main"):
    risks, readings, audit = result_lookups(result)
    registry = channel_registry(channels)
    selected_id = next((row["sector_id"] for row in sectors.to_dict("records") if row["sector"] == selected), None)
    svg = ['<svg viewBox="0 0 134 120" role="img" aria-label="Croquis de finca; sectores según riesgo y canales con pérdidas estimadas" xmlns="http://www.w3.org/2000/svg">',
           '<title>Croquis de finca sin georreferenciación. El detalle se elige con el selector de sector.</title>',
           '<defs><marker id="farm-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0 L10 5 L0 10" fill="#2875a0"/></marker></defs>',
           '<rect x="28" y="9" width="100" height="100" rx="1.5" fill="#f7faf7" stroke="#bdccc1" stroke-width=".5"/>',
           '<text x="78" y="6" font-size="2.8" text-anchor="middle" fill="#536961">FINCA · CUADRÍCULA RELATIVA 0–100</text>']
    for value in [20, 40, 60, 80]:
        svg.append(f'<path d="M{28 + value} 9 V109 M28 {9 + value} H128" stroke="#e2e9e3" stroke-width=".2"/>')
    inlet = result["audit"].sort_values("orden_recorrido").iloc[0]["caudal_entrada_ls"] if result is not None else None
    svg.append(f'<text x="1" y="5" font-size="2.4" fill="#256f99">ENTRADA {f"{inlet:.1f} L/s" if inlet is not None else "pendiente"}</text>')
    svg.append('<path d="M22 7 V14" stroke="#2875a0" stroke-width="1" marker-end="url(#farm-arrow)"/>')
    taps = {}
    for i, channel in enumerate(registry):
        cid = channel["canal_id"]
        y0, y1 = 14 + i * 22, 36 + i * 22
        taps[cid] = y1
        row = audit.get(cid)
        loss = row["perdida_ia_pct"] if row else None
        state = channel_state(loss)
        color = CHANNEL_COLORS[state]
        loss_text = f'{loss:.1f}% pérdida IA' if loss is not None else 'Sin resultado'
        flow_text = f'Sale {row["caudal_salida_ls"]:.1f} L/s' if row else 'Caudal pendiente'
        label = str(channel["tramo"])
        svg.append(f'<g class="farm-channel channel-{state}" data-canal-id="{cid}" data-loss="{loss if loss is not None else ""}">'
                   f'<title>{safe(label)}: {safe(loss_text)}; {safe(flow_text)}</title>'
                   f'<path d="M22 {y0} V{y1}" stroke="{color}" stroke-width="1.3" fill="none"/>'
                   f'<circle cx="22" cy="{y1}" r="1" fill="{color}"/>'
                   f'<text x="1" y="{y0 + 6}" font-size="2.5" fill="{color}" font-weight="600">{safe(label[:18])}</text>'
                   f'<text x="1" y="{y0 + 10}" font-size="2.1" fill="#536961">{safe(loss_text)}</text>'
                   f'<text x="1" y="{y0 + 14}" font-size="2.1" fill="#536961">{safe(flow_text)}</text></g>')
    # Conexiones lógicas: no se reparte ni descuenta caudal por sector.
    for row in sectors.to_dict("records"):
        x, y = 28 + row["x"], 9 + row["y"] + row["alto"] / 2
        tap = taps[row["canal_id"]]
        svg.append(f'<path class="farm-connection" data-sector-id="{safe(row["sector_id"])}" data-canal-id="{safe(row["canal_id"])}" d="M22 {tap} H26 V{y} H{x}" stroke="#2875a0" stroke-width=".5" stroke-dasharray="1 .7" fill="none" marker-end="url(#farm-arrow)"/>')
    for row in sectors.to_dict("records"):
        name, sid = row["sector"], row["sector_id"]
        diagnosis = risks.get(name)
        state = sector_state(diagnosis)
        fill, ink = SECTOR_COLORS[state]
        risk = diagnosis["riesgo_deficit_ia_0_100"] if diagnosis else None
        score = f'{risk:.0f}/100' if risk is not None and pd.notna(risk) else 'Pendiente'
        priority = f'P{diagnosis["orden_propuesto"]}' if diagnosis else ''
        x, y, w, h = row["x"] + 28, row["y"] + 9, row["ancho"], row["alto"]
        font = min(3.2, w / 7, h / 4.2)
        crop = str(row["cultivo"])
        label = str(name)
        max_chars = max(6, int(w / (font * .52)))
        shown = label if len(label) <= max_chars else label[:max_chars - 1] + '…'
        stroke = '#213b35' if sid == selected_id else ink
        svg.append(f'<g class="farm-sector risk-{state}" data-sector-id="{safe(sid)}" data-sector-name="{safe(name)}" data-risk="{risk if risk is not None else ""}">'
                   f'<title>{safe(name)} · {safe(crop)} · {row["area_ha"]:.2f} ha · Riesgo {score} · {priority}</title>'
                   f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="1" fill="{fill}" stroke="{stroke}" stroke-width="{.85 if sid == selected_id else .35}"/>'
                   f'<text x="{x + w / 2}" y="{y + h / 2 - font}" text-anchor="middle" font-size="{font}" fill="{ink}" font-weight="600">{safe(shown)}</text>'
                   f'<text x="{x + w / 2}" y="{y + h / 2 + font * .5}" text-anchor="middle" font-size="{font * .75}" fill="#536961">{safe(crop[:max_chars])} · {row["area_ha"]:.1f} ha</text>'
                   f'<text x="{x + w / 2}" y="{y + h / 2 + font * 1.85}" text-anchor="middle" font-size="{font * .85}" fill="{ink}">Riesgo {score} · {priority}</text></g>')
    svg.append('</svg>')
    badge = '<p class="map-preview">Vista previa · aplicá o guardá la configuración para incorporarla.</p>' if preview else ''
    return (badge + '<div class="farm-canvas">' + ''.join(svg).replace('farm-arrow', 'farm-arrow-' + canvas_id) + '</div>'
            '<div class="farm-legend" aria-label="Leyenda"><span><i class="low"></i>Verde · Normal &lt;45</span><span><i class="medium"></i>Amarillo · Advertencia 45–69</span><span><i class="high"></i>Rojo · Crítico ≥70</span><span><i class="unknown"></i>Gris · Información insuficiente</span></div>'
            '<p class="farm-caption">Canales: azul &lt;10% · amarillo 10–19% · rojo ≥20% de pérdida IA. Líneas discontinuas: asociación lógica, sin reparto hidráulico por sector. Croquis relativo; la superficie se declara aparte.</p>')


def sector_detail_html(sectors, channels, result, selected):
    row = sectors.set_index("sector").loc[selected]
    risks, readings, audit = result_lookups(result)
    risk, sensor, channel = risks.get(selected), readings.get(selected), audit.get(row["canal_id"])
    names = {r["canal_id"]: r["tramo"] for r in channel_registry(channels)}
    def measured(key, fmt):
        return fmt.format(sensor[key]) if sensor is not None and pd.notna(sensor.get(key)) else "NO DISPONIBLE"
    score = f'{risk["riesgo_deficit_ia_0_100"]:.1f} / 100' if risk and pd.notna(risk["riesgo_deficit_ia_0_100"]) else "Pendiente"
    pairs = [("Cultivo", row["cultivo"]), ("Superficie declarada", f'{row["area_ha"]:.2f} ha'),
             ("Humedad virtual", measured("humedad_suelo_pct", "{:.2f}%")),
             ("Temperatura suelo", measured("temperatura_suelo_c", "{:.1f} °C")),
             ("Conductividad", measured("ec_ds_m", "{:.2f} dS/m")),
             ("Sensor", sensor["estado_sensor"] if sensor else "Sin resultado actual"),
             ("Riesgo IA", score), ("Confianza", risk["confianza"] if risk else "Pendiente"),
             ("Canal asociado", names[row["canal_id"]]),
             ("Pérdida del canal", f'{channel["perdida_ia_pct"]:.2f}%' if channel else "Pendiente"),
             ("Prioridad propuesta", str(risk["orden_propuesto"]) if risk else "Pendiente")]
    alert = ''
    if risk and channel and pd.notna(risk["riesgo_deficit_ia_0_100"]) and risk["riesgo_deficit_ia_0_100"] >= 70 and channel["perdida_ia_pct"] >= 20:
        alert = '<p class="farm-coincidence">Existe coincidencia entre riesgo hídrico alto y pérdidas elevadas en el tramo asociado. No demuestra que la pérdida causó el estrés.</p>'
    if row["sensor_disponible"] == 0:
        alert += '<p class="farm-caption">Sin sensor físico no existe medición directa de humedad; la IA estima riesgo mediante clima e historial.</p>'
    return f'<section class="farm-detail"><h3>{safe(selected)}</h3><dl>' + ''.join(f'<div><dt>{safe(k)}</dt><dd>{safe(v)}</dd></div>' for k, v in pairs) + '</dl>' + alert + '<small>SENSOR VIRTUAL / DATO DE PRUEBA</small></section>'


def recommendation_html(result):
    if result is None:
        return '<p class="empty-note">Analizá la finca para actualizar la recomendación.</p>'
    p = result["priority"]
    eligible = p[(p["confianza"] != "BAJA") & (p["restriccion"] == "Ninguna") & p["riesgo_deficit_ia_0_100"].notna()]
    text = (f'Priorizar {safe(eligible.iloc[0]["sector"])} en la revisión del próximo turno: riesgo {eligible.iloc[0]["riesgo_deficit_ia_0_100"]:.1f}/100.'
            if len(eligible) else 'Revisión humana requerida: faltan datos suficientes para una recomendación firme.')
    repair = result["audit"].iloc[0]
    return f'<section class="farm-recommendation"><h3>Recomendación actual</h3><p>{text}</p><p>Reparación sugerida: <strong>{safe(repair["tramo"])}</strong>, por su relación entre agua recuperable y costo.</p><small>El encargado acepta, modifica o rechaza. Compuertas manuales.</small></section>'
