"""SVG de un croquis relativo: visualiza resultados existentes, no realiza hidráulica ni GIS."""
from __future__ import annotations

from html import escape
import pandas as pd

from .farm import channel_registry

BLOCK_COLORS = {"low": ("#86cf9b", "#4f9a67", "#3d8155", "#0d2a1c"), "medium": ("#f5c84c", "#cf9c1f", "#ad7f12", "#2e2000"),
                "high": ("#ee7565", "#c84a3c", "#a5382c", "#330b07"), "unknown": ("#b9c2bd", "#8f9b95", "#77837d", "#1c2824")}
CHANNEL_COLORS = {"low": "#17608a", "medium": "#c08a0c", "high": "#b3322e", "unknown": "#5a6663"}
CHANNEL_INK = {"low": "#14506f", "medium": "#6e4a05", "high": "#8f2622", "unknown": "#3f524b"}
ISO_X, ISO_Y = .87, .5
ORIGIN = (126, 24)
CANAL_X = -8


def iso(x, y, z=0):
    """Proyecta la cuadrícula relativa 0–100 a pantalla. Es un dibujo, no un cálculo geográfico."""
    return round(ORIGIN[0] + (x - y) * ISO_X, 2), round(ORIGIN[1] + (x + y) * ISO_Y - z, 2)


def poly(*corners):
    return " ".join(f"{a},{b}" for a, b in corners)


def path(*corners):
    return "M" + " L".join(f"{a} {b}" for a, b in corners)


def block_height(state, risk):
    # Sin dato confiable el bloque queda bajo: la altura solo representa riesgo estimado.
    return 3 if state == "unknown" else round(4 + float(risk) * .14, 2)


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
    svg = ['<svg viewBox="0 0 222 134" role="img" aria-label="Croquis isométrico de finca; sectores según riesgo y canales con pérdidas estimadas" xmlns="http://www.w3.org/2000/svg">',
           '<title>Croquis isométrico sin georreferenciación. El detalle se elige con el selector de sector.</title>',
           '<defs><marker id="farm-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0 L10 5 L0 10" fill="#2875a0"/></marker></defs>',
           f'<polygon class="farm-slab-side" points="{poly(iso(0, 100), iso(100, 100), iso(100, 100, -2.5), iso(0, 100, -2.5))}"/>',
           f'<polygon class="farm-slab-edge" points="{poly(iso(100, 0), iso(100, 100), iso(100, 100, -2.5), iso(100, 0, -2.5))}"/>',
           f'<polygon class="farm-ground" points="{poly(iso(0, 0), iso(100, 0), iso(100, 100), iso(0, 100))}"/>']
    for value in [20, 40, 60, 80]:
        svg.append(f'<path class="farm-grid" d="{path(iso(value, 0), iso(value, 100))} {path(iso(0, value), iso(100, value))}"/>')
    for x, y, label in [(90, -7, "X 0–100"), (107, 50, "Y 0–100")]:
        a, b = iso(x, y)
        svg.append(f'<text x="{a}" y="{b}" font-size="2.8" text-anchor="middle" class="farm-axis">{label}</text>')
    inlet = result["audit"].sort_values("orden_recorrido").iloc[0]["caudal_entrada_ls"] if result is not None else None
    a, b = iso(CANAL_X, -9)
    svg.append(f'<text x="{a - 3}" y="{b - 1}" font-size="3.3" font-weight="600" text-anchor="end" fill="#14506f">Entrada {f"{inlet:.1f} L/s" if inlet is not None else "pendiente"}</text>')
    svg.append(f'<path d="{path(iso(CANAL_X, -9), iso(CANAL_X, -1))}" stroke="#2875a0" stroke-width="1.2" fill="none" marker-end="url(#farm-arrow)"/>')
    taps = {}
    channel_svg = []
    for i, channel in enumerate(registry):
        cid = channel["canal_id"]
        t0, t1 = i * 25, (i + 1) * 25
        taps[cid] = t1
        row = audit.get(cid)
        loss = row["perdida_ia_pct"] if row else None
        state = channel_state(loss)
        color = CHANNEL_COLORS[state]
        loss_text = f'{loss:.1f}% pérdida IA' if loss is not None else 'Sin resultado'
        flow_text = f'Sale {row["caudal_salida_ls"]:.1f} L/s' if row else 'Caudal pendiente'
        label = str(channel["tramo"])
        route = path(iso(CANAL_X, t0), iso(CANAL_X, t1))
        # El grosor sigue al caudal que entra al tramo según el balance ya calculado.
        width = round(.8 + 3.2 * float(row["caudal_entrada_ls"]) / float(inlet), 2) if row and inlet else 2.4
        a, b = iso(CANAL_X, (t0 + t1) / 2)
        a -= 12  # Deja libre el canal, que baja en diagonal hacia la izquierda.
        c, d = iso(CANAL_X, t1)
        channel_svg.append(f'<g class="farm-channel channel-{state}" data-canal-id="{cid}" data-loss="{loss if loss is not None else ""}">'
                           f'<title>{safe(label)}: {safe(loss_text)}; {safe(flow_text)}</title>'
                           f'<path d="{route}" stroke="#5f7167" stroke-width="{width + 1.2}" stroke-linecap="round" fill="none"/>'
                           f'<path d="{route}" stroke="{color}" stroke-width="{width}" fill="none"/>'
                           f'<path class="farm-water" d="{route}" fill="none"/>'
                           f'<circle cx="{c}" cy="{d}" r="1.5" fill="{color}"/>'
                           f'<text x="{a}" y="{b - 4}" font-size="3.4" text-anchor="end" fill="{CHANNEL_INK[state]}" font-weight="700">{safe(label[:16])}</text>'
                           f'<text x="{a}" y="{b}" font-size="2.9" text-anchor="end" class="farm-axis">{safe(loss_text)}</text>'
                           f'<text x="{a}" y="{b + 4}" font-size="2.9" text-anchor="end" class="farm-axis">{safe(flow_text)}</text></g>')
    # Conexiones lógicas: no se reparte ni descuenta caudal por sector.
    for row in sectors.to_dict("records"):
        middle = row["y"] + row["alto"] / 2
        tap = taps[row["canal_id"]]
        route = path(iso(CANAL_X, tap), iso(-4, tap), iso(-4, middle), iso(row["x"], middle))
        svg.append(f'<path class="farm-connection" data-sector-id="{safe(row["sector_id"])}" data-canal-id="{safe(row["canal_id"])}" d="{route}" stroke="#17608a" stroke-width=".8" stroke-dasharray="1.6 1.1" fill="none" marker-end="url(#farm-arrow)"/>')
    svg.extend(channel_svg)
    # Se pintan de atrás hacia adelante para que los bloques cercanos tapen a los lejanos.
    for row in sorted(sectors.to_dict("records"), key=lambda r: r["x"] + r["ancho"] / 2 + r["y"] + r["alto"] / 2):
        name, sid = row["sector"], row["sector_id"]
        diagnosis = risks.get(name)
        state = sector_state(diagnosis)
        top, left, right, ink = BLOCK_COLORS[state]
        risk = diagnosis["riesgo_deficit_ia_0_100"] if diagnosis else None
        score = f'{risk:.0f}/100' if risk is not None and pd.notna(risk) else 'Pendiente'
        priority = f'P{diagnosis["orden_propuesto"]}' if diagnosis else ''
        x, y, w, d = row["x"], row["y"], row["ancho"], row["alto"]
        h = block_height(state, risk)
        font = min(3.4, min(w, d) / 6)
        crop = str(row["cultivo"])
        label = str(name)
        max_chars = max(6, int((w + d) * ISO_X * .62 / (font * .52)))
        shown = label if len(label) <= max_chars else label[:max_chars - 1] + '…'
        chosen = sid == selected_id
        cx, cy = iso(x + w / 2, y + d / 2, h)
        svg.append(f'<g class="farm-sector risk-{state}{" is-selected" if chosen else ""}" data-sector-id="{safe(sid)}" data-sector-name="{safe(name)}" data-risk="{risk if risk is not None else ""}" data-box="{x} {y} {w} {d}">'
                   f'<title>{safe(name)} · {safe(crop)} · {row["area_ha"]:.2f} ha · Riesgo {score} · {priority}</title>'
                   f'<polygon fill="{left}" points="{poly(iso(x, y + d, h), iso(x + w, y + d, h), iso(x + w, y + d), iso(x, y + d))}"/>'
                   f'<polygon fill="{right}" points="{poly(iso(x + w, y, h), iso(x + w, y + d, h), iso(x + w, y + d), iso(x + w, y))}"/>'
                   f'<polygon fill="{top}" stroke="{"#17352a" if chosen else right}" stroke-width="{.9 if chosen else .3}" stroke-linejoin="round" points="{poly(iso(x, y, h), iso(x + w, y, h), iso(x + w, y + d, h), iso(x, y + d, h))}"/>'
                   f'<text x="{cx}" y="{cy - font * 1.5}" text-anchor="middle" font-size="{font}" fill="{ink}" font-weight="700">{safe(shown)}</text>'
                   f'<text x="{cx}" y="{cy - font * .2}" text-anchor="middle" font-size="{font * .75}" fill="{ink}">{safe(crop[:max_chars])} · {row["area_ha"]:.1f} ha</text>'
                   f'<text x="{cx}" y="{cy + font * 1.05}" text-anchor="middle" font-size="{font * .8}" fill="{ink}" font-weight="600">Riesgo {score} · {priority}</text></g>')
    svg.append('</svg>')
    badge = '<p class="map-preview">Vista previa. Aplicá o guardá la configuración para incorporarla.</p>' if preview else ''
    return (badge + '<div class="farm-canvas">' + ''.join(svg).replace('farm-arrow', 'farm-arrow-' + canvas_id) + '</div>'
            '<div class="farm-legend" aria-label="Leyenda"><span><i class="low"></i>Verde · Normal &lt;45</span><span><i class="medium"></i>Amarillo · Advertencia 45–69</span><span><i class="high"></i>Rojo · Crítico ≥70</span><span><i class="unknown"></i>Gris · Información insuficiente</span></div>'
            '<p class="farm-caption">Cuanto más alto el bloque, mayor el riesgo estimado. El grosor del canal sigue al caudal que queda en cada tramo. Canales: azul &lt;10% · amarillo 10–19% · rojo ≥20% de pérdida IA. Líneas discontinuas: asociación lógica, sin reparto hidráulico por sector. Croquis relativo; la superficie se declara aparte.</p>')


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
