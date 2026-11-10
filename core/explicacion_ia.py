"""Explicación en lenguaje natural con la API de Claude. No predice ni decide: redacta sobre resultados ya calculados."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

import anthropic
from dotenv import load_dotenv
import pandas as pd

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
MODEL = "claude-opus-5-5"
REPORT_SECTIONS = ("Datos analizados", "Pérdidas significativas", "Cómo distribuir el agua",
                   "Inversión en reparaciones", "Cómo se llegó a esto", "Datos a revisar")
SIGNIFICANT_LOSS_PCT = 20  # Mismo umbral que pinta un tramo en rojo en el mapa.
SYSTEM_PROMPT = """Sos el asistente de riego de una finca mendocina con riego por gravedad. Le escribís un informe al encargado.
Recibís un JSON con resultados ya calculados por modelos locales con datos sintéticos: riesgo por sector, reparto de minutos propuesto y pérdidas por tramo de canal.
Escribí en español rioplatense y en Markdown, en menos de 350 palabras, sin tablas y con listas cortas, con exactamente estos títulos de nivel 3 y en este orden:
### Datos analizados
Escenario, cantidad de sectores, cuántos tienen lectura de sonda y eficiencia del canal.
### Pérdidas significativas
Los tramos cuya pérdida alcanza el umbral indicado en el JSON, con porcentaje y litros perdidos. Si ninguno lo alcanza, decilo.
### Cómo distribuir el agua
El orden y los minutos propuestos por sector, y qué sectores quedan para inspección antes de regar y por qué.
### Inversión en reparaciones
Repartir el turno de otra forma no reduce lo que pierde un tramo: en este sistema la única forma de bajar esa pérdida es repararlo. La reparación sugerida es siempre el tramo con prioridad_reparacion 1, porque rinde más litros por peso, aunque su pérdida no llegue al umbral: nombralo primero con su costo y los litros que recuperaría, aclarando el supuesto de recuperación. Después decí si hay tramos con pérdida significativa donde no queda otra solución que reparar para dejar de perder esa agua, con su costo y litros recuperables. Si ningún tramo tiene pérdida significativa, decí que no hay una pérdida que obligue a invertir ahora.
### Cómo se llegó a esto
En un máximo de cinco viñetas breves y con datos del JSON: qué entradas recibió el modelo de cada sector, cómo la regla de prioridad convirtió el riesgo en orden y minutos, y cómo se calcularon las pérdidas y el ranking de reparación. No atribuyas el resultado a una variable puntual salvo que los valores lo muestren claramente. Aclará que los números los calcularon los modelos locales y que vos solo redactás.
### Datos a revisar
Mediciones faltantes o de confianza BAJA.
Reglas: usá solo los datos recibidos y no cambies las cifras. Escribí litros y pesos sin decimales y con punto de miles (1.728.000 L, $850.000 ARS). La marca (VIRTUAL) en la humedad indica que la lectura viene de la sonda simulada de la demo: es lo esperado, no un problema a revisar. No inventes mediciones, precios del agua ni plazos de recupero. Si la humedad figura NO DISPONIBLE, decilo. Si riesgo y pérdidas coinciden, no afirmes que una causa la otra. Es una propuesta: el encargado decide y opera las compuertas a mano."""


OPINION_PROMPT = """Sos el asistente de riego de una finca mendocina con riego por gravedad. El encargado leyó tu informe y no está de acuerdo.
Recibís un JSON con los datos calculados, tu informe previo, la conversación hasta ahora y su objeción.
Respondé en español rioplatense, en Markdown sin títulos y en menos de 180 palabras, con tu opinión honesta sobre esa objeción: decí si tiene razón, en qué sí y en qué no, y qué consecuencia tendría hacer lo que propone según los datos.
Si el JSON indica parte_en_discusion, opiná solo sobre esa parte. Si trae cambio_propuesto, comentá ese reparto sin calcular sus efectos.
Si conoce algo del campo que los datos no muestran, reconocelo: esos datos son sintéticos y él está en la finca.
Reglas: usá solo los datos recibidos y no cambies las cifras. Escribí litros y pesos sin decimales y con punto de miles. No inventes mediciones ni recalcules minutos o pérdidas: si su cambio requiere otro cálculo, decí que no lo podés estimar. La decisión final es suya y las compuertas se operan a mano."""


REVISION_PROMPT = """Sos el asistente de riego de una finca mendocina con riego por gravedad. El encargado revisó tu informe, aceptó algunas partes y cambió otras.
Recibís un JSON con los datos calculados, tu informe previo, sus decisiones por parte y lo que conversaron.
Reescribí el informe final en español rioplatense, en Markdown, en menos de 250 palabras, sin tablas y con listas cortas, con exactamente estos títulos de nivel 3 y en este orden:
### Qué decidió el encargado
Qué aceptó, qué cambió y por qué, si dio un motivo.
### Reparto final
Los minutos finales por sector, tal como figuran en sus decisiones, y cuáles difieren de la propuesta.
### Reparación
Si la aceptó o la rechazó, con costo y litros recuperables. Si la rechazó, recordá que la pérdida de ese tramo sigue igual mientras no se repare.
### Qué no se recalculó
Aclará que los modelos no volvieron a calcular riesgo ni pérdidas con los minutos cambiados.
Reglas: sus decisiones mandan y no las discutas de nuevo. No cambies ninguna cifra ni estimes efectos de los cambios. Escribí litros y pesos sin decimales y con punto de miles. Las compuertas se operan a mano."""


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    # El JSON estable y sin NaN evita enviar valores inválidos a la API.
    return json.loads(df[columns].to_json(orient="records", force_ascii=False))


def build_payload(result: dict, scenario: str) -> str:
    sectors = _records(result["priority"], ["orden_propuesto", "sector", "riesgo_deficit_ia_0_100", "estado", "confianza", "modo",
                                            "humedad_directa", "tiempo_sugerido_min", "restriccion", "advertencias"])
    channels = _records(result["audit"], ["prioridad_reparacion", "tramo", "perdida_ia_pct", "agua_perdida_l",
                                          "litros_recuperables_si_repara", "costo_reparacion_ars", "l_recuperables_por_1000_ars"])
    farm = result["sectors"].set_index("sector")
    for row, raw in zip(sectors, result["priority"]["entradas_modelo"]):
        row["entradas_modelo"] = json.loads(raw)
        row["cultivo"], row["area_ha"] = str(farm.loc[row["sector"], "cultivo"]), float(farm.loc[row["sector"], "area_ha"])
    route = result["audit"].sort_values("orden_recorrido")
    water_in, water_out = float(route.iloc[0]["agua_entrada_l"]), float(route.iloc[-1]["agua_salida_l"])
    return json.dumps({"escenario": scenario, "origen": "DATOS SINTÉTICOS DE DEMOSTRACIÓN", "sectores": sectors, "canales": channels,
                       "sectores_con_lectura_de_sonda": int(result["sectors"]["humedad_suelo_pct"].notna().sum()),
                       "agua_entrada_l": water_in, "agua_salida_l": water_out, "eficiencia_canal_pct": round(water_out / water_in * 100, 1),
                       "umbral_perdida_significativa_pct": SIGNIFICANT_LOSS_PCT,
                       "nota_cultivo": "El cultivo y la superficie se informan, pero los modelos de riesgo no usan el cultivo.",
                       "regla_prioridad": str(result["priority"].iloc[0]["regla_prioridad"]),
                       "metodo_canales": "Un Random Forest estima el porcentaje de pérdida de cada tramo; los litros se calculan en secuencia con caudal × tiempo; el ranking ordena por litros recuperables cada 1000 ARS.",
                       "supuesto_recuperacion": "reparar recupera el 70% de la pérdida local; sin validación de campo"},
                      ensure_ascii=False, sort_keys=True)


def split_report(text: str) -> dict:
    """Separa el informe por sus títulos. Si el modelo no respetó alguno, devuelve vacío y se muestra entero."""
    parts = re.split(r"^###\s+(.+?)\s*$", text or "", flags=re.MULTILINE)
    sections = {title.strip(): body.strip() for title, body in zip(parts[1::2], parts[2::2])}
    return sections if all(title in sections for title in REPORT_SECTIONS) else {}


def is_unavailable(text: str) -> bool:
    """Los avisos de error o de falta de análisis no son contenido de la IA y no se guardan como tal."""
    return not text or text.startswith(("**Informe no disponible", "**Opinión no disponible", "Analizá"))


def _ask_claude(system: str, content: str, noun: str, client=None) -> str:
    if client is None:
        load_dotenv(ENV_PATH, override=True)
        if not os.getenv("ANTHROPIC_API_KEY"):
            return f"**{noun} no disponible:** falta `ANTHROPIC_API_KEY` en el archivo `.env`. El análisis local sigue funcionando."
        client = anthropic.Anthropic(timeout=90.0, max_retries=1)
    try:
        response = client.beta.messages.create(
            model=MODEL, max_tokens=16000, output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system, messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError:
        return f"**{noun} no disponible:** la API rechazó la key configurada en `.env`."
    except anthropic.PermissionDeniedError:
        return f"**{noun} no disponible:** la key no tiene permiso para usar este modelo."
    except anthropic.RateLimitError:
        return f"**{noun} no disponible:** se alcanzó el límite de uso de la API. Probá de nuevo en un momento."
    except anthropic.APIConnectionError:
        return f"**{noun} no disponible:** no se pudo conectar con la API. Revisá la conexión."
    except anthropic.APIStatusError as exc:
        return f"**{noun} no disponible:** la API respondió con el error {exc.status_code}."
    if response.stop_reason == "refusal":
        return f"**{noun} no disponible:** el modelo no generó una respuesta para esta solicitud."
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or f"**{noun} no disponible:** la API devolvió una respuesta vacía."


def explain_turn(result: dict | None, scenario: str, client=None) -> str:
    if result is None:
        return "Analizá la finca antes de consultar a la IA."
    text = _ask_claude(SYSTEM_PROMPT, build_payload(result, scenario), "Informe", client)
    return text


def opine_on_objection(result: dict | None, scenario: str, report: str, objection: str, exchanges: list | None = None, client=None,
                       part: str | None = None, proposed: list | None = None) -> str:
    """Responde al desacuerdo del encargado sin cambiar cifras ni tomar la decisión por él."""
    if result is None:
        return "Analizá la finca antes de consultar a la IA."
    content = json.dumps({"datos": json.loads(build_payload(result, scenario)), "informe_previo": report, "conversacion_previa": exchanges or [],
                          "parte_en_discusion": part, "cambio_propuesto": proposed, "objecion_del_encargado": objection},
                         ensure_ascii=False, sort_keys=True)
    return _ask_claude(OPINION_PROMPT, content, "Opinión", client)


def revise_report(result: dict, scenario: str, report: str, parts: dict, exchanges: list | None = None, client=None) -> str:
    """Rehace el informe con lo que decidió el encargado. Las cifras nuevas vienen de sus decisiones, no del modelo."""
    content = json.dumps({"datos": json.loads(build_payload(result, scenario)), "informe_previo": report,
                          "decisiones_del_encargado": parts, "conversacion": exchanges or []}, ensure_ascii=False, sort_keys=True)
    return _ask_claude(REVISION_PROMPT, content, "Informe", client)
