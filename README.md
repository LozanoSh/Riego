# Asistente Inteligente de Riego Intrafinca — Mendoza

MVP académico en **Python + Gradio + scikit-learn** para revisar sectores de una finca, simular sensores y comparar pérdidas de canales antes de decidir un turno de riego por gravedad.

**DATOS DE PRUEBA — DEMOSTRACIÓN ACADÉMICA.** Se usan sensores virtuales y datos sintéticos. No hay validación de campo ni automatización de compuertas.

Orden: **Lozano → Siccardi → Sosa → Rivamar**. Esta versión corresponde a la **Etapa 1 de Juan Ignacio Lozano**.

## Qué permite

- Arrancar con cinco sectores y trabajar con **1–10**, agregando, eliminando o editando fichas y un croquis superior.
- Editar clima, condiciones de suelo, historial, restricciones y riego hipotético.
- Ver un gemelo digital horario de humedad, temperatura de suelo y EC, con ruido reproducible.
- Sin sensor: humedad **NO DISPONIBLE**, riesgo por modelo proxy y confianza **BAJA**.
- Ejecutar tres Random Forest reales: riesgo con sensor, riesgo sin sensor y pérdida porcentual por tramo.
- Ver entradas, MAE, R², importancia de variables, recorrido del agua y comparación económica.
- Conservar H1 y la trazabilidad temporal del MVP; la decisión final pertenece al encargado.

## Instalación y ejecución

Python **3.12+**. Verificado en Linux con Python 3.12.3; las dependencias directas están fijadas en `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

En este workspace `.venv` ya está preparado:

```bash
source .venv/bin/activate
python app.py
```

También se puede ejecutar `./iniciar_linux_mac.sh`, que utiliza pip o uv en un entorno propio. Si Debian/Ubuntu informa que falta ensurepip, instalar `python3-venv` o crear el entorno con `uv venv .venv` e instalar con `uv pip install --python .venv/bin/python -r requirements.txt`.

En Windows: doble clic en `iniciar_windows.bat`, o:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Abrir **http://127.0.0.1:7860**. El entrenamiento inicial tarda unos segundos; el resumen inicial ya muestra una simulación real del escenario Normal. Si el puerto está ocupado, Gradio informa otro en la terminal; se puede fijar con `GRADIO_SERVER_PORT`.

Solo la instalación requiere descargar paquetes. La simulación y las predicciones funcionan localmente, sin APIs pagas.

## Interfaz

- **Resumen:** seis tarjetas importantes, croquis y recomendación; sin tablas ni parámetros internos.
- **Mapa de la finca:** vista superior SVG, conexiones, detalle lateral y configuración de cada sector.
- **Finca:** tarjetas y sensor virtual temporal seleccionable.
- **Clima y simulación:** clima, horizonte y escenarios.
- **Canales:** recorrido del agua, comparación económica y editor avanzado.
- **IA:** predicciones, explicaciones, importancia y métricas de los tres Random Forest.
- **Decisión humana:** H1/H2/H3 existentes y trazabilidad temporal desplegable.
- **Datos técnicos:** tablas completas conservadas para revisión.
- **Arquitectura:** funcionamiento actual y evolución futura.

La acción común es **ANALIZAR FINCA**. En pantallas pequeñas las pestañas restantes están en **…**; tablas y croquis tienen desplazamiento dentro de su panel.

## Cómo usar el mapa

1. Desde Resumen, presionar **VER MAPA COMPLETO**.
2. En **Ver detalle de**, elegir un sector: el panel muestra lecturas virtuales, riesgo, confianza, canal y prioridad.
3. En **Configurar finca**, usar **AGREGAR SECTOR** o **ELIMINAR SECTOR**. El cambio actualiza mapa, sensores, IA, tablas y resumen.
4. Editar nombre, cultivo, superficie, sensor o canal asociado. En **CONFIGURACIÓN AVANZADA DEL SECTOR**, editar X/Y, ancho/alto, EC, NDVI e historial.
5. Los cambios de posición/tamaño/canal muestran una **vista previa**. **APLICAR SECTOR Y ANALIZAR**, **ANALIZAR FINCA** o **GUARDAR CONFIGURACIÓN** los incorpora. Aplicar antes de cambiar de sector.
6. **GUARDAR CONFIGURACIÓN** guarda la ficha, distribución y características de canales en `data/finca_config.json`.
7. **CARGAR CONFIGURACIÓN GUARDADA** recupera esos datos y recalcula con el clima actual. **CARGAR FINCA DEMO** y **RESTAURAR FINCA DE DEMOSTRACIÓN** restablecen los cinco sectores originales.

Cuadrícula relativa 0–100: origen arriba a la izquierda; ancho/alto entre 10 y 50; el sector debe caber completo dentro del rectángulo. Se avisan superposiciones. La superficie es declarada y no se calcula a partir del croquis. Los IDs de canales son estables por posición del recorrido; renombrar un tramo no rompe la asociación.

**No es GIS:** no hay coordenadas GPS, mapas externos, imágenes satelitales ni cálculo geográfico de áreas. Las líneas discontinuas son relaciones lógicas; no se reparte caudal por sector ni se simulan ramales hidráulicos.

## Demo rápida

1. Revisar Resumen y abrir el mapa.
2. Agregar Sector F; seleccionar y eliminar Sector C; restaurar demo.
3. Elegir Sector B, moverlo con X=60/Y=12 y cambiar Canal asociado a Tramo D. Aplicar, guardar, restaurar y cargar la configuración para comprobar persistencia.
4. En Clima probar Normal, Zonda / estrés, Falla sensor y Canal deteriorado. Los presets conservan geometría y asociaciones; los botones de restauración restablecen toda la demo.
5. En Falla sensor, seleccionar Sector C: humedad **NO DISPONIBLE**, confianza BAJA y color gris, aunque el proxy pueda estimar riesgo.
6. En Canales, desplegar el editor y cambiar fuga/costo. Las líneas y etiquetas del mapa se actualizan con las pérdidas predichas y el balance existente.
7. En IA revisar métricas e importancia. En Decisión humana registrar una respuesta explícita; Sin respuesta sigue pendiente.

Sectores: verde <45, amarillo 45–<70, rojo ≥70 de riesgo; gris si faltan datos o hay confianza BAJA. Canales: azul <10%, amarillo 10–<20%, rojo ≥20% de pérdida. El cruce de alto riesgo y pérdidas altas se presenta como **coincidencia**, sin afirmar causalidad.

## Rangos y unidades

Rangos orientativos para la demostración agrícola mendocina, según el pedido de la etapa; no son una calibración agronómica:

- Clima: 0–42 °C; humedad relativa 10–90%; viento 0–70 km/h; lluvia 0–40 mm/día; ET0 1–12 mm/día.
- Suelo: humedad 5–45%; temperatura 5–35 °C; EC 0,2–4,5 dS/m; NDVI 0,15–0,90; días desde riego 0–14.
- Canales: caudal inicial 5–120 L/s; turno 1–24 h; longitudes 50–2000 m; índices 0–1; reparación $100.000–$5.000.000 ARS.

La lluvia y ET0 se convierten a tasas horarias; el turno se muestra en horas y se convierte a minutos internamente. El horizonte del sensor (0–48 h) es independiente del turno. Las salidas del gemelo digital se limitan al rango de la demo; entradas de sonda anómalas se descartan, no se corrigen como si fueran mediciones válidas.

## Código

```text
app.py                     Interfaz y callbacks de Gradio
assets/dashboard.css       Presentación y adaptación a móvil
core/simulation.py         Orquestación y alta/baja de sectores
core/sensors.py            Gemelo digital horario
core/synthetic_data.py     CSV, presets y datasets reproducibles
core/ai_models.py          Tres Random Forest y métricas
core/agents.py             Calidad, diagnóstico, prioridad y auditor de canales
core/decision.py           H1 y trazabilidad temporal existentes
core/farm.py               Geometría, asociación y JSON local
core/farm_map.py           Croquis SVG y detalle por sector
core/visuals.py             Tarjetas, gráficos y diagramas
```

[Documentación de Lozano](docs/ETAPA_1_LOZANO.md) · [Mapa del proyecto](docs/MAPA_PROYECTO.md) · [Desarrollo lineal](docs/TRABAJO_LINEAL.md).

## Verificación de esta etapa

Con el entorno activado:

```bash
python -m unittest discover -s tests -v
# Con la app activa en otra terminal:
python -m tests.smoke_gradio
```

Hay **36 pruebas** de regresión y un smoke contra Gradio: alta/baja, geometría, asociaciones, colores, guardado/carga, presets, clima, fuga, costo, importancias y restauración. Se verificó el croquis por navegador en 1920×1080 y el resumen y el mapa móviles en 390×844; las capturas están en [docs/evidencia](docs/evidencia). La suite final de entrega corresponde a Rivamar.

## Límites y continuidad

Modelos básicos entrenados con datos sintéticos; el riesgo puede saturarse cerca de 100. Confianza por reglas, sin calibración estadística. Las importancias son globales. El sensor es virtual y su balance es didáctico. Sentinel-2 es un indicador indirecto y no mide directamente humedad del suelo. Se supone que reparar recupera el 70% de la pérdida local. La eficiencia es el cociente entre agua de salida y entrada, no la meta del 15%, que sigue pendiente de validación.

La apertura/cierre de compuertas ocurre fuera del sistema. H1 y M1–M11 se conservan sin completar todavía el flujo integral ni persistencia. Las fichas/canales se conservan si se usa GUARDAR CONFIGURACIÓN; las decisiones H1 siguen siendo temporales. El JSON es un archivo único y el último guardado reemplaza el anterior. El arranque siempre muestra la demo; cargar lo guardado es explícito. Windows y macOS no se probaron en sus sistemas.

Siccardi continúa con evaluación, features, métricas, explicabilidad y confianza. Sosa con agentes, decisiones y registro persistente; Rivamar con integración y entrega final.

## Integrantes y uso de IA

1. Juan Ignacio Lozano — base funcional, simulador e interfaz.
2. Gian Franco Siccardi — IA, evaluación y explicabilidad.
3. Jeremías Sosa — agentes, decisiones y trazabilidad.
4. Santiago Rivamar — integración final y entrega.

ChatGPT apoyó organización, implementación, revisión y documentación. El equipo debe verificar y reelaborar los supuestos y decisiones antes de entregar; esta documentación no acredita una revisión humana aún no realizada.
