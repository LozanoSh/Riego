# Etapa 1 — Juan Ignacio Lozano

Actualizada el **4 de noviembre de 2026**. Orden: **Lozano → Siccardi → Sosa → Rivamar**.

## Qué construí

Una evolución del MVP Python + Gradio existente: dashboard con resumen, mapa editable y detalles en pestañas, sectores dinámicos, formularios de edición, gemelo digital temporal, IA básica real y auditor de canales con recorrido visual. Se conservaron los modelos Random Forest, los agentes y los controles humanos útiles. No se cambió de tecnología ni se agregó infraestructura. La ampliación de croquis y guardado local se documenta en «Mapa editable de finca».

Plan aplicado: revisar código/CSV/documentación; separar simulación y sensor; eliminar el límite fijo de cinco; alinear rangos y datasets; reorganizar la UI; comprobar altas/bajas, escenarios y entradas; revisar escritorio/móvil y documentar el handoff. No se hizo tuning ni comparación avanzada de modelos.

## Sectores dinámicos

- El CSV inicial contiene **cinco sectores** de Vid, Olivo y Frutal.
- `normalize_sectors` admite **1–10**, exige nombres únicos y valida campos.
- `add_sector` genera el primer nombre libre (por ejemplo Sector F) y una ficha inicial coherente: Vid, 27% humedad, 22 °C suelo, EC 1,2, NDVI 0,60 y cinco días desde riego.
- `remove_sector` elimina el elegido y selecciona otro existente; no permite eliminar el último.
- Ambos botones recalculan sensores, predicciones, prioridades, tablas y tarjetas. Al llegar a los límites se deshabilita la acción correspondiente; el backend también aplica el límite.
- Los presets conservan cantidad, identidad, cultivo y superficie, y restablecen el resto de las entradas de demostración. Falla de sensor afecta al Sector C si existe; si no, al primer sector. Restaurar base vuelve a los cinco originales.
- La ficha se guarda al simular o aplicar. **Aplicar antes de cambiar el selector**; elegir otro sector carga sus datos guardados. Las ediciones sin aplicar no se persisten.

La lógica usa filas y nombres, no arrays de longitud cinco. Las pruebas ejecutan fincas de uno y diez sectores y escenarios con un único sector.

## Rangos orientativos utilizados

Son límites del pedido para una demo agrícola mendocina defendible; no representan una calibración por cultivo, suelo, ubicación ni estación.

| Entrada | Rango de demo | Valor inicial |
|---|---|---|
| Temperatura ambiente | 0–42 °C | 24 |
| Humedad relativa | 10–90% | 40 |
| Viento | 0–70 km/h | 12; Zonda 45 |
| Lluvia | 0–40 mm/día | 0 |
| ET0 | 1–12 mm/día | 5,5; Zonda 9,5 |
| Humedad de suelo | 5–45% | 24–30 según sector |
| Temperatura de suelo | 5–35 °C | 21–25 |
| EC | 0,2–4,5 dS/m | 0,9–1,6 |
| NDVI | 0,15–0,90 | 0,46–0,72 |
| Días desde riego | 0–14 | 3–8 |
| Caudal inicial | 5–120 L/s | 60 |
| Turno | 1–24 h | 8 |
| Longitud por tramo | 50–2000 m | 350–900 |
| Permeabilidad/fuga/sedimento | 0–1 | valores de los CSV |
| Reparación | $100.000–$5.000.000 ARS | $650.000–$1.550.000 |

Los controles y el backend validan las entradas. El sensor aplica clamps en sus salidas de humedad, temperatura y EC para mantenerse en los límites de la demo. Una entrada de sonda fuera de rango se descarta como LECTURA ANÓMALA; no se presenta un clamp como lectura válida. Las features faltantes no se inventan. Los generadores sintéticos cubren los nuevos rangos; el caudal local de los tramos puede caer por debajo de 5 L/s, por lo que el entrenamiento de canales incluye caudales desde 0,1 L/s.

## Arquitectura

```text
app.py → core/simulation.py
             ├─ normalización (agents.py)
             ├─ gemelo digital (sensors.py)
             ├─ calidad → IA → diagnóstico → prioridad
             └─ IA de canales → balance → ranking económico

core/synthetic_data.py → CSV + presets + datasets con semilla fija
core/ai_models.py      → entrenamiento de los tres Random Forest
core/visuals.py        → tarjetas, gráficos y diagramas
assets/dashboard.css  → tokens, jerarquía y responsive
core/decision.py      → H1 y M1–M11 existentes
```

`simulation.py` no depende de Gradio. `app.py` mantiene callbacks y componentes. El auditor de canales sigue en `ChannelAuditAgent` para evitar un refactor innecesario. Se conserva el alias `synthetic_data.simulate_sensors` para consumidores de la etapa anterior.

La pestaña Arquitectura distingue **MVP actual** (sensor virtual → app → IA → dashboard) de **implementación futura** (sensor físico → gateway → API → IA → dashboard). Esta última es una propuesta, no infraestructura implementada.

## Interfaz

- **Resumen:** seis tarjetas, croquis, una recomendación principal y acceso al mapa completo. Sin tablas ni parámetros técnicos.
- **Mapa de la finca:** croquis grande, selector y detalle lateral; configuración compartida de sectores, geometría y canal; guardado/carga/restauración.
- **Finca:** tarjetas de sectores y una curva temporal seleccionable, con lecturas virtuales.
- **Clima y simulación:** cinco variables, horizonte y los cuatro presets existentes.
- **Canales:** recorrido, eficiencia, comparación de reparaciones y editor avanzado plegado.
- **IA:** predicciones, explicaciones, importancias y métricas.
- **Decisión humana:** controles H1/H2/H3 existentes y M1–M11 dentro de un desplegable.
- **Datos técnicos:** configuración completa, lecturas, calidad, predicciones, prioridades y balance completo.
- **Arquitectura:** finca → sectores → sensores → datos → IA → diagnóstico → prioridad; en paralelo canales → IA de pérdidas → reparación; recomendaciones al humano.

Se conservó toda la información; la edición agronómica se trasladó de Finca al formulario de Mapa para tener una única ficha por sector. Las tablas completas dejaron el Resumen y están en Datos técnicos. La eficiencia y disponibilidad de sensores siguen en Canales/Finca; el Resumen prioriza los seis indicadores solicitados.

Colores acompañados por texto, tipografía Source Sans Pro local y un botón común **ANALIZAR FINCA**. En móvil las pestañas adicionales están en **…**. Las tablas y el croquis tienen desplazamiento interno cuando hace falta, sin ampliar el documento. Los gráficos de sensores/IA se refrescan al abrir su pestaña para ajustar el ancho.

Las ediciones agronómicas invalidan resultados anteriores. Mover/reasociar muestra una **vista previa**, sin modificar el modelo ni los datos guardados; Analizar, Aplicar o Guardar incorpora el cambio y recalcula. H1 compara la configuración vigente con la propuesta y bloquea registrar una propuesta desactualizada.

## Sensor virtual y simulación

`simulate_sensors` produce una fila por hora y sector, con humedad, temperatura, EC, estado y origen **SENSOR VIRTUAL / DATO DE PRUEBA**.

El balance horario es didáctico: secado proporcional a ET0/24 y modulado por temperatura, viento y humedad ambiente; aporte de lluvia/24 y de `riego_simulado_mm_h`. La temperatura del suelo se aproxima al aire; EC cambia suavemente con secado/aporte. Se añade ruido reproducible sin acumularlo como estado interno.

Estados: NORMAL, ADVERTENCIA, SIN SENSOR y LECTURA ANÓMALA. Sin sonda no se generan humedad, temperatura ni EC. Se muestran NO DISPONIBLE, riesgo proxy y confianza BAJA. El gráfico no inventa una curva en ese caso. Las lecturas anómalas también se descartan.

La última lectura del horizonte alimenta la IA. Lluvia y ET0 son tasas diarias; el horizonte (0–48 h) es independiente de la duración del turno. El riego es **hipotético** y no opera ni aprueba compuertas. NDVI e historial quedan constantes durante el horizonte; `riego_ultimo_turno` es metadato y los modelos mínimos usan días/turnos sin regar.

## IA básica operativa

Tres `RandomForestRegressor`: 160 árboles, profundidad máxima 11 y hoja mínima de tres. Split 80/20 con semilla 42; semillas de bosques y generadores fijas. Se entrenan en memoria al iniciar. La inferencia ejecuta `predict`; no sustituye el modelo por las fórmulas de generación sintética.

| Modelo | Dataset total | Train / test | MAE | R² |
|---|---:|---:|---:|---:|
| Riesgo con sensor | 7000 | 5600 / 1400 | 3,384 | 0,874 |
| Riesgo sin sensor | 7000 | 5600 / 1400 | 5,258 | 0,858 |
| Pérdida del canal | 6000 | 4800 / 1200 | 1,013 | 0,975 |

**Las métricas corresponden al dataset sintético y no representan precisión validada en campo.**

Con sensor se usan clima, ET0, NDVI, días desde riego, turnos sin regar, humedad, temperatura de suelo y EC. Sin sensor se excluyen las tres lecturas de suelo: la salida es riesgo, nunca humedad. Si falta otra entrada necesaria, se informa SIN PREDICCIÓN, sin imputación silenciosa.

Las features exactas se leen de `feature_names_in_`; sus valores individuales aparecen en el detalle del diagnóstico. `feature_importances_` genera el gráfico real, sin porcentajes prefijados. La confianza sigue siendo una regla simple de calidad; no es una probabilidad ni tiene calibración estadística.

No se compararon algoritmos ni se optimizaron hiperparámetros: queda para Siccardi.

## Canales y separación de responsabilidades

- **IA:** porcentaje de pérdida, limitado a un rango válido.
- **Cálculo:** litros de entrada = L/s × horas × 3600. Cada tramo recibe el agua remanente del anterior. La IA usa su caudal local.
- **Supuesto:** reparar recupera el 70% de la pérdida local, sin validación de campo.
- **Regla económica:** litros recuperables / costo × 1000; ordena reparaciones y no forma parte del ML.
- **Eficiencia del resumen:** agua final / agua inicial × 100. No representa ahorro real ni cumplimiento de la hipótesis del 15%.
- **Humano:** revisa la recomendación y opera compuertas manualmente.

El tramo más crítico se elige por mayor pérdida porcentual; la reparación conveniente por litros/costo. Pueden ser distintos. En Normal son Tramo D y Tramo A respectivamente.

## Cómo ejecutar y usar la demo

```bash
source .venv/bin/activate
python app.py
```

Para instalar en otra máquina con Python 3.12+: `python3 -m venv .venv`, activar entorno e instalar `python -m pip install -r requirements.txt`. También están los scripts Linux/macOS y Windows. Abrir http://127.0.0.1:7860.

1. Revisar Resumen, disponible desde el arranque, y presionar VER MAPA COMPLETO.
2. En Mapa agregar Sector F; eliminarlo y comprobar que vuelve a cinco.
3. Editar nombre/humedad o desactivar la sonda y aplicar/analizar.
4. En Clima usar Zonda; volver a Normal; probar Falla sensor y Canal deteriorado.
5. En Canales desplegar el editor: fuga del Tramo B a 1; costo del C a 100000; simular cada cambio.
6. Mostrar el diagnóstico, alternar importancia de los tres modelos y explicar la arquitectura.
7. Restaurar escenario base para volver a los cinco sectores y valores iniciales.

## Pruebas de la etapa

```bash
python -m unittest discover -s tests -v
# Con la app activa:
python -m tests.smoke_gradio
```

**36 pruebas de regresión aprobadas (24 existentes + 12 del croquis).** El smoke usa el servicio real de Gradio y comprueba altas/bajas, cuatro presets, cambios de clima/fuga/costo, tres importancias, restauración y H1 pendiente.

| Caso | Resultado |
|---|---|
| Normal | Cinco lecturas por hora, cinco riesgos y cuatro pérdidas válidas; resumen calculado. |
| Alta / baja | 5 → 6 → 5 por navegador y HTTP; tablas, curva, ficha e IA se actualizan. |
| Límites | Núcleo y navegador probados con 1 y 10; botones deshabilitados en sus límites y backend con error claro ante una operación fuera de ellos. |
| Presets dinámicos | Cuatro presets también ejecutados con un único sector. |
| Zonda | Riesgo medio 73,02 → 99,88; riesgo máximo 97,1 → 100,0. |
| Falla de sensor | Sector C: humedad NO DISPONIBLE, confianza BAJA, modelo proxy; sin curva ni temperatura/EC ficticias. |
| Canal deteriorado | Tramo B: pérdida 24,79% → 28,84%. |
| Fuga / costo | Aumentar fuga eleva pérdida; costo C = 100000 lo pone primero sin alterar la pérdida IA. |
| Clima y ficha | Editar temperatura a 35 °C, renombrar a Lote Norte y desactivar sensor funcionan por controles reales del navegador. |
| Invalidación | Editar muestra Cambios pendientes y vacía predicciones; H1 bloquea datos desactualizados. |
| Rango / faltantes | Se rechazan valores fuera de límites; clamps de sensor; sin NDVI no se inventa riesgo; sin EC se usa proxy. |
| Reproducibilidad | Generadores y evolución temporal repetibles con las mismas entradas. |

Revisión visual en navegador aislado con motor Chromium/Brave: **1365×950 y 390×844**. Se corrigió el encabezado móvil y se comprobó ausencia de desborde horizontal del documento en Resumen/Finca. No se detectaron errores JavaScript en los recorridos revisados. Capturas en [evidencia](evidencia): [Resumen](evidencia/resumen-desktop.png), [móvil](evidencia/resumen-movil.png), [sin sensor](evidencia/sensor-sin-dato.png), [curva](evidencia/sensor-evolucion.png), [canales](evidencia/canales.png), [arquitectura](evidencia/arquitectura.png).

No es la suite final de Rivamar ni una auditoría completa de accesibilidad o navegadores. No se verificó ejecución en Windows/macOS ni una instalación de sistema operativo limpio.

## Problemas conocidos y límites

- El objetivo sintético puede saturar el riesgo cerca de 100; Normal define clima moderado, no garantiza que todos los sectores estén saludables.
- Los rangos son orientativos; no hay calibración por suelo/cultivo/estación ni medición de campo.
- El bosque no garantiza monotonía para cualquier combinación arbitraria de valores.
- Importancias globales, no explicaciones locales o causales; confianza sin calibración avanzada.
- Los campos de ficha y geometría sin aplicar se descartan al elegir otro sector; se informa en la propia interfaz.
- Presets restablecen datos de prueba; las fichas se guardan con GUARDAR CONFIGURACIÓN. H1 y trazabilidad siguen siendo temporales.
- Sentinel-2 no mide humedad directamente; el NDVI es simulado. No hay sensores físicos, gateways, API externa ni compuertas automáticas.
- El 70% recuperable y la meta del 15% son supuestos/hipótesis pendientes de validación.

## Archivos modificados y creados

Modificados: `app.py`, `core/synthetic_data.py`, `core/agents.py`, `core/decision.py`, ambos CSV, `README.md`, `docs/ETAPA_1_LOZANO.md`, `docs/MAPA_PROYECTO.md`, `docs/TRABAJO_LINEAL.md`, `docs/GUIA_DEFENSA.md`, `tests/test_etapa_1.py` y `tests/smoke_gradio.py`.

Creados: `core/simulation.py`, `core/sensors.py`, `core/visuals.py`, `assets/dashboard.css` y capturas en `docs/evidencia/`. `core/ai_models.py`, requisitos y scripts de arranque conservan su implementación útil de la versión anterior.

## Qué recibe Siccardi

Una aplicación ejecutable, UI organizada, sectores 1–10, rangos explícitos, CSV editables, generadores reproducibles, tres modelos reales y pipeline probado. Puede concentrarse directamente en la IA.

Pendientes de su etapa:

1. Auditar features, targets, split y saturación del riesgo; revisar representatividad del dataset.
2. Comparar modelos y agregar evaluación más completa, sin rehacer el dashboard.
3. Mejorar explicabilidad y confianza; revisar valores fuera del dominio del entrenamiento.
4. Revisar el auditor de canales y sus métricas.
5. Documentar sus cambios en `docs/ETAPA_2_SICCARDI.md` para Sosa.

Se conserva H1/M1–M11, sin completar trazabilidad persistente ni flujo humano integral. La evaluación avanzada corresponde a Siccardi; los agentes/registro integral a Sosa; la integración, pruebas finales y ZIP a Rivamar.

## Mapa editable de finca

### Representación y alcance

`core/farm_map.py` genera **SVG nativo dentro de `gr.HTML`**. La finca es un rectángulo; los sectores son rectángulos en una cuadrícula relativa 0–100. No se agregaron dependencias, GIS, GPS, imágenes, Leaflet, Google Maps, Mapbox ni cálculo geográfico de superficies. La superficie en hectáreas se declara y no deriva del tamaño dibujado.

No hay drag-and-drop: inputs numéricos de X/Y, ancho/alto y un selector de canal ofrecen una interacción simple y estable. X crece a la derecha; Y hacia abajo. Ancho/alto admiten 10–50 y el rectángulo debe caber completo dentro de 0–100. Los valores inválidos producen una advertencia sin corromper la finca. Las superposiciones se avisan y se permite corregirlas; no se resuelve geometría catastral.

El croquis no sustituye la simulación: lee los resultados que ya produce el MVP. El entrenamiento, hiperparámetros, métricas, confianza y fórmulas del sensor/canales no se modificaron. Se compararon las huellas del código del entrenamiento y de los generadores antes/después: coinciden.

### Sectores e identificadores

Cada sector conserva sus campos agronómicos y suma `sector_id`, `x`, `y`, `ancho`, `alto`, `canal_id`. El identificador de sector permanece al renombrarlo. Agregar busca un espacio inicial libre sin desplazar las ubicaciones del usuario; si no lo hay, se avisa una posible superposición. El rango sigue siendo 1–10 y los cambios se reflejan en mapa, ficha, sensores, simulación, IA y tablas.

Los escenarios conservan geometría y canal asociado. **Restaurar finca de demostración**, **Cargar finca demo** y el reset de escenario restablecen cinco sectores, geometría, cultivos, asociaciones, canales y sensores originales. Cargar un JSON es una acción explícita: el arranque siempre usa la demo, aunque exista una configuración guardada.

### Canales y flujo

Los cuatro tramos tienen IDs estables `canal-a`, `canal-b`, `canal-c`, `canal-d`, correspondientes a las cuatro posiciones del recorrido existente. Renombrar un tramo cambia su etiqueta, no sus asociaciones. La demo relaciona A→A, B→B, C→B, D→C, E→D. El selector muestra los nombres actuales y guarda el ID.

El mapa muestra entrada, canal principal, tramos y conexiones discontinuas a sectores. Los porcentajes provienen de `ChannelAuditAgent`; caudales y remanentes provienen del balance existente. Las ramas son **asociaciones lógicas**: no se reparte ni descuenta caudal por sector ni se modela hidráulica de ramales. No debe interpretarse que todo el caudal remanente del tramo llega a cada sector asociado.

### Colores y detalle

- Sectores: verde <45, amarillo 45–<70, rojo ≥70 de riesgo IA. Gris si falta resultado, predicción o la confianza es BAJA. Sin sensor no aparece humedad ficticia, aunque el proxy pueda producir riesgo.
- Canales: azul <10%, amarillo 10–<20%, rojo ≥20% de pérdida IA; gris si no hay resultado actual.
- El panel lateral muestra cultivo, superficie, lecturas virtuales, estado del sensor, riesgo, confianza, canal, pérdida y prioridad.
- Si riesgo ≥70 y pérdida asociada ≥20%, aparece: **«Existe coincidencia entre riesgo hídrico alto y pérdidas elevadas en el tramo asociado»**, aclarando que no demuestra que la pérdida causó el estrés. Es una regla descriptiva, no otro modelo de IA.

### Guardado y carga

`core/farm.py` valida y guarda **`data/finca_config.json`**. Incluye versión, nombre de demo, los sectores completos con geometría y sensores iniciales, y características de los cuatro tramos. No guarda predicciones como si fueran observaciones ni persiste decisiones H1. Los faltantes se serializan como `null`, con JSON estricto.

El archivo se escribe temporalmente en el mismo directorio y luego se reemplaza de forma atómica. GUARDAR CONFIGURACIÓN aplica la ficha y la geometría actuales, analiza y guarda; CARGAR CONFIGURACIÓN GUARDADA valida antes de aplicar y recalcula con el clima actual. El clima, caudal inicial, duración e historial de predicciones no se incluyen en ese JSON. El archivo es único y compartido: el último guardado reemplaza el anterior.

Una versión incompatible, ID de canal inválido, geometría fuera de límite o JSON incompleto da un error claro y conserva la finca actual. Guardar de nuevo sobrescribe el archivo local, sin base de datos.

### Verificación del croquis

| Prueba solicitada | Comprobación |
|---|---|
| 1 · Finca demo | Cinco rectángulos, cuatro tramos y cinco conexiones; datos reales del pipeline en SVG. |
| 2 · Agregar F | Aparece en mapa, ficha, sensores, IA y resumen; probado en núcleo, HTTP y navegador. |
| 3 · Eliminar C | Desaparece del mapa, predicciones e historial; probado en núcleo y navegador. |
| 4 · Mover B | X=60, Y=12 actualiza la vista previa; aplicar incorpora geometría sin alterar el riesgo IA. |
| 5 · Cambiar canal de B | Selector a Tramo D cambia la conexión y el detalle; nombre/ID se conservan al guardar/cargar. |
| 6 · Cambiar riesgo de A | Humedad inicial 40% y cero días desde riego producen menor riesgo real del RF y pasan el sector de amarillo a verde. No se edita ni hardcodea la predicción. |
| 7 · Pérdidas de B | Fuga 0→1 cruza un umbral de color del canal con predicciones del modelo existente. |
| 8 · Guardar/cargar | GUI y HTTP recuperan geometría y asociaciones después de restaurar; JSON mantiene lecturas ausentes como null. |
| 9 · Restaurar | Vuelven cinco sectores y la distribución original. La configuración entregada se deja en demo. |

Además: persistencia temporal probada en archivo aislado, configuración inválida rechazada, estado gris sin sensor y mensaje no causal verificados automáticamente. El smoke HTTP preserva el archivo previo al test.

Revisión visual del croquis en 1920×1080 y del resumen/mapa en móvil 390×844. Se confirmó documento de 390 px y desplazamiento solo dentro del panel del croquis. Se mantiene SVG con desplazamiento interno en móvil; el detalle se selecciona por lista, no haciendo click sobre rectángulos. Las capturas nuevas están en `docs/evidencia/mapa-*.png`.

### Archivos de esta ampliación y continuidad

Nuevos: `core/farm.py`, `core/farm_map.py`, `data/finca_config.json`, `tests/test_farm_map.py` y capturas del mapa. Modificados: `app.py`, `core/agents.py`, `core/synthetic_data.py` (solo carga/presets), `core/visuals.py`, `data/sectores_demo.csv`, `assets/dashboard.css`, tests existentes y documentación.

Siccardi recibe la finca configurable y la relación sector/canal como metadatos disponibles. Puede revisar features, explicaciones y confianza sin rehacer el mapa. No se adelantaron su selección de modelos ni los registros persistentes de turnos de Sosa o la entrega final de Rivamar.
