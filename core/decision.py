from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo
import pandas as pd

VALID_DECISIONS = ["Aceptar", "Modificar", "Rechazar", "Sin respuesta"]
SAVED_DECISIONS = ["Aceptar", "Modificar"]
AGREE, WATER_CHANGE, REPAIR_NO = "De acuerdo", "No, quiero cambiarlo", "No la haría ahora"
WATER_PART, REPAIR_PART = "Reparto del agua", "Reparación"
EDIT_COLUMNS = ["Sector", "Propuesto (min)", "Tus minutos"]
DECISIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "decisiones.json"


def build_protocol_trace(priority_df: pd.DataFrame, quality_df: pd.DataFrame, decision: str = "Pendiente", note: str = "") -> pd.DataFrame:
    top = priority_df.iloc[0]["sector"] if len(priority_df) else "sin propuesta"
    low_quality = quality_df[quality_df["confianza_datos"] == "BAJA"]["sector"].tolist()
    quality_msg = "datos válidos" if not low_quality else f"baja confianza en: {', '.join(low_quality)}"

    rows = [
        ["M1", "Productor → Agente de Datos", "INFORMAR", f"ficha de {len(priority_df)} sectores y variables del lote", "completo"],
        ["M2", "Encargado → Agente de Datos", "PEDIR", "evaluar turno", "completo"],
        ["M3", "Agente de Datos → Diagnóstico", "INFORMAR", quality_msg, "completo"],
        ["M4", "Diagnóstico → Priorización", "INFORMAR", "riesgo hídrico relativo por sector", "completo"],
        ["M5", "Priorización → Encargado", "PROPONER", f"orden y tiempos; primer sector sugerido: {top}", "completo"],
        ["M6", "Encargado → Priorización", "PEDIR", "ampliar explicación (opcional)", "disponible"],
        ["M7", "Priorización → Encargado", "INFORMAR", "fuentes, límites y confianza", "completo"],
        ["M8", "Encargado → Registro", "DECISIÓN H1", f"{decision}. {note}".strip(), "pendiente" if decision in ["Pendiente", "Sin respuesta"] else "registrado"],
        ["M9", "Encargado → Registro", "INFORMAR", "sectores efectivamente regados", "pendiente"],
        ["M10", "Registro → Productor", "INFORMAR", "reporte del turno", "pendiente"],
        ["M11", "Registro → Encargado", "INFORMAR", "registro y cierre", "pendiente"],
    ]
    return pd.DataFrame(rows, columns=["mensaje", "flujo", "tipo", "contenido", "estado"])


def register_human_decision(decision: str, modified_order: str, note: str) -> tuple[str, pd.DataFrame]:
    if decision not in VALID_DECISIONS:
        decision = "Sin respuesta"
    now = datetime.now(ZoneInfo("America/Argentina/Mendoza")).isoformat(timespec="seconds")

    if decision == "Sin respuesta":
        status = "PENDIENTE / TURNO SIN PLAN: el silencio no implica aceptación ni habilita riego."
    elif decision == "Aceptar":
        status = "ACEPTADA por el encargado (H1). La apertura de compuertas sigue siendo manual (H2)."
    elif decision == "Modificar":
        status = f"MODIFICADA por el encargado (H1). Nuevo orden declarado: {modified_order or 'no especificado'}."
    else:
        status = "RECHAZADA por el encargado (H1). Se requiere criterio manual/inspección si corresponde (H3)."

    log = pd.DataFrame([{
        "fecha_hora": now,
        "decision_humana": decision,
        "orden_modificado": modified_order,
        "observacion": note,
        "estado": status,
    }])
    return status, log


def water_edit_table(result: dict) -> pd.DataFrame:
    p = result["priority"]
    return pd.DataFrame({EDIT_COLUMNS[0]: p["sector"].tolist(), EDIT_COLUMNS[1]: p["tiempo_sugerido_min"].round(1).tolist(),
                         EDIT_COLUMNS[2]: p["tiempo_sugerido_min"].round(1).tolist()})


def read_water_edit(table, result: dict, turn_minutes: float) -> list:
    """Valida el reparto del encargado: es su decisión, pero tiene que caber en el turno y respetar las restricciones."""
    df = pd.DataFrame(table)
    if not set(EDIT_COLUMNS).issubset(df.columns):
        raise ValueError("Falta la tabla de minutos. Volvé a consultar a la IA.")
    minutes = pd.to_numeric(df[EDIT_COLUMNS[2]], errors="coerce")
    if minutes.isna().any() or (minutes < 0).any():
        raise ValueError("Completá los minutos de cada sector con números iguales o mayores a cero.")
    priority = result["priority"].set_index("sector")
    if sorted(df[EDIT_COLUMNS[0]].astype(str)) != sorted(priority.index.astype(str)):
        raise ValueError("Los sectores de la tabla no coinciden con el análisis. Volvé a consultar a la IA.")
    rows = [{"sector": str(sector), "minutos": round(float(value), 1)} for sector, value in zip(df[EDIT_COLUMNS[0]], minutes)]
    blocked = [r["sector"] for r in rows if r["minutos"] > 0 and priority.loc[r["sector"], "restriccion"] == "No regar"]
    if blocked:
        raise ValueError(f"{', '.join(blocked)} tiene la restricción No regar. Dejalo en 0 o quitá la restricción en el mapa.")
    if abs(sum(r["minutos"] for r in rows) - turn_minutes) > 1:
        raise ValueError(f"Los minutos suman {sum(r['minutos'] for r in rows):.0f} y el turno tiene {turn_minutes:.0f}. Ajustalos para que coincidan.")
    if all(abs(r["minutos"] - float(priority.loc[r["sector"], "tiempo_sugerido_min"])) < .05 for r in rows):
        raise ValueError("No cambiaste ningún minuto. Modificá la tabla o marcá De acuerdo.")
    return rows


def _last_reason(exchanges: list, part: str):
    return next((e["objecion"] for e in reversed(exchanges or []) if e.get("parte") == part), None)


def build_parts(water: str, repair: str, table, exchanges: list, result: dict, turn_minutes: float) -> dict:
    original = [{"sector": r["sector"], "minutos": round(float(r["tiempo_sugerido_min"]), 1)} for _, r in result["priority"].iterrows()]
    changed = water == WATER_CHANGE
    fix = result["audit"].iloc[0]
    return {"reparto": {"decision": "cambiado" if changed else "de_acuerdo", "original": original,
                        "final": read_water_edit(table, result, turn_minutes) if changed else original,
                        "motivo": _last_reason(exchanges, WATER_PART) if changed else None},
            "reparacion": {"decision": "rechazada" if repair == REPAIR_NO else "de_acuerdo", "tramo": str(fix["tramo"]),
                           "costo_ars": float(fix["costo_reparacion_ars"]), "litros_recuperables": float(fix["litros_recuperables_si_repara"]),
                           "motivo": _last_reason(exchanges, REPAIR_PART) if repair == REPAIR_NO else None}}


def parts_changed(parts: dict) -> bool:
    return parts["reparto"]["decision"] != "de_acuerdo" or parts["reparacion"]["decision"] != "de_acuerdo"


def parts_summary(parts: dict) -> str:
    water = "Reparto cambiado" if parts["reparto"]["decision"] == "cambiado" else "Reparto aceptado"
    repair = "reparación rechazada" if parts["reparacion"]["decision"] == "rechazada" else "reparación aceptada"
    return f"{water}, {repair}"


def decision_record(decision: str, modified_order: str, note: str, scenario: str, result: dict, report: str = "", exchanges: list | None = None,
                    parts: dict | None = None, final_report: str = "") -> dict:
    """Foto de lo que el encargado aceptó: la propuesta calculada, no una medición ni un riego ejecutado."""
    plan = result["priority"][["orden_propuesto", "sector", "riesgo_deficit_ia_0_100", "confianza", "tiempo_sugerido_min", "accion_sugerida"]]
    repair = result["audit"].iloc[[0]][["tramo", "perdida_ia_pct", "costo_reparacion_ars", "litros_recuperables_si_repara"]]
    return {
        "fecha_hora": datetime.now(ZoneInfo("America/Argentina/Mendoza")).isoformat(timespec="seconds"),
        "decision": decision, "orden_modificado": modified_order.strip(), "observacion": note.strip(), "escenario": scenario,
        "plan": json.loads(plan.to_json(orient="records", force_ascii=False)),
        "reparacion_sugerida": json.loads(repair.to_json(orient="records", force_ascii=False))[0],
        "informe_ia": report.strip() or None,
        "conversacion": exchanges or [],
        "partes": parts,
        "informe_final": final_report.strip() or None,
    }


def load_decisions(path=DECISIONS_PATH) -> list:
    path = Path(path)
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("El historial de decisiones no es un JSON válido; no se modificó.") from exc
    if not isinstance(records, list):
        raise ValueError("El historial de decisiones no tiene el formato esperado; no se modificó.")
    return records


def save_decision(record: dict, path=DECISIONS_PATH) -> Path:
    if record.get("decision") not in SAVED_DECISIONS:
        raise ValueError("Solo se guardan las propuestas aceptadas.")
    path = Path(path)
    records = load_decisions(path) + [record]
    encoded = json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            out.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path


def decisions_view(records: list) -> pd.DataFrame:
    columns = ["Fecha", "Decisión", "Escenario", "Plan elegido", "Reparación sugerida", "Observación"]
    rows = [[r.get("fecha_hora", "").replace("T", " ")[:16],
             "Aceptada con cambios" if r.get("decision") == "Modificar" else "Aceptada", r.get("escenario", ""),
             r.get("orden_modificado") or (r.get("plan") or [{}])[0].get("sector", ""),
             (r.get("reparacion_sugerida") or {}).get("tramo", "") + (" (rechazada)" if ((r.get("partes") or {}).get("reparacion") or {}).get("decision") == "rechazada" else ""),
             r.get("observacion", "")] for r in reversed(records)]
    return pd.DataFrame(rows, columns=columns)
