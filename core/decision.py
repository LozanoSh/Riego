from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

VALID_DECISIONS = ["Aceptar", "Modificar", "Rechazar", "Sin respuesta"]


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
