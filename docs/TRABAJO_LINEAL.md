# Desarrollo lineal — cuatro integrantes

Orden acordado: **Lozano → Siccardi → Sosa → Rivamar**. Cada integrante recibe una versión ejecutable y documentada antes de iniciar su etapa.

## 1) Juan Ignacio Lozano — Base funcional, simulador e IA mínima operativa

- Conservar el MVP y sus módulos.
- Iniciar con cinco sectores editables (1–10), cuatro canales, dashboard con croquis editable, guardado JSON y detalles por pestañas y presets Normal/Zonda/Falla de sensor/Canal deteriorado.
- Implementar gemelo digital horario con ruido reproducible y modo sin sensor sin humedad inventada.
- Integrar Random Forest real, predicciones, métricas e importancia de variables.
- Mostrar pérdidas, recorrido del agua y reglas económicas por separado.
- Conservar decisión humana y compuertas manuales.
- Probar A–E y documentar la etapa.

**Handoff a Siccardi:** `docs/ETAPA_1_LOZANO.md`, datasets, modelos, interfaz, pipeline y pruebas funcionando. Comparación avanzada, explicabilidad y confianza quedan para Siccardi.

## 2) Gian Franco Siccardi — IA, evaluación, explicabilidad y confianza

**Recibe:** la etapa de Lozano. Leer primero `docs/ETAPA_1_LOZANO.md`.

- Auditar modelos, features, targets, train/test y posibles fugas de datos.
- Comparar como máximo Random Forest, árbol y Gradient Boosting; reportar MAE, RMSE y R².
- Mantener modelos con sensor y proxy claramente separados.
- Mejorar confianza por reglas de calidad, explicabilidad y detección de entradas fuera del entrenamiento.
- Revisar dataset sintético y auditor IA de canales.
- Dejar casos saludable, estrés y sin sensor.

**Handoff a Sosa:** `docs/ETAPA_2_SICCARDI.md`, modelos elegidos, métricas, límites y casos reproducibles. No rediseñar la interfaz ni adelantar el registro completo de turnos.

## 3) Jeremías Sosa — Agentes, decisiones humanas, trazabilidad y fallas

**Recibe:** base funcional de Lozano e IA revisada por Siccardi. Leer las etapas 1 y 2.

- Separar responsabilidades de Datos, Diagnóstico, Priorización y Alertas/Registro.
- Completar protocolo M1–M11 y flujo H1/H2/H3.
- Registrar aceptación, modificación, rechazo y sectores efectivamente regados, sin controlar hardware.
- Tratar fuentes incompletas, silencio, turno sin plan y discrepancias con revisión humana.
- Revisar continuidad entre turnos para no ignorar reiteradamente un sector de riesgo alto.
- Integrar alertas de pérdidas de canales sin afirmar causalidad comprobada.
- Guardar turnos en JSON/CSV local.

**Handoff a Rivamar:** `docs/ETAPA_3_SOSA.md`, agentes, decisiones y registros probados. No rehacer el ML ni adelantar la entrega final.

## 4) Santiago Rivamar — Integración final, interfaz, pruebas y entrega

**Recibe:** las tres etapas anteriores. Leer sus documentos antes de modificar.

- Verificar instalación desde cero y flujo completo de datos → IA → humano → registro.
- Revisar la interfaz y el panel resumen recibidos sin cambiar la lógica.
- Validar Normal, Zonda, sensor fallando y canal deteriorado.
- Comprobar decisiones humanas y persistencia, y agregar las pruebas finales mínimas.
- Preparar README final, arquitectura, guion de cinco minutos y división de defensa.
- Preparar ZIP, CSV, requisitos y capturas de respaldo.

**Entrega final:** aplicación estable, pruebas end-to-end, guía de demo, limitaciones visibles y respaldo listo para presentar.

## Regla de trabajo

No completar tareas de la etapa siguiente. Conservar lo útil, documentar problemas y entregar una versión ejecutable. La IA recomienda; el encargado decide y opera manualmente las compuertas.
