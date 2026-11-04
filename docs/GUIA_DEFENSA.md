# Guía de defensa — 5 minutos

Actualización Lozano: el escenario base tiene cinco sectores y admite 1–10. La demo vigente y sus límites están documentados en `ETAPA_1_LOZANO.md`; esta guía conserva la estructura oral del equipo.

## 0:00–0:45 · Problema
"Las fincas mendocinas con riego por gravedad reciben un turno limitado. El encargado debe decidir cómo repartirlo entre sectores con información incompleta. Nuestro sistema no reemplaza al encargado: organiza datos, estima riesgo y propone prioridades."

## 0:45–1:35 · Sensor virtual y datos
Mostrar Mapa de la finca para configurar y Finca para la evolución del sensor. `sensor_disponible=1` habilita una sonda virtual de humedad/temperatura/EC, sin afirmar que haya un sensor físico conectado. Si no existe sensor, se usan clima + NDVI + historial como proxies y baja la confianza; no se inventa una humedad.

## 1:35–2:25 · IA
- Random Forest #1: riesgo de déficit por sector con sensor.
- Random Forest #2: riesgo de déficit sin sensor directo.
- Random Forest #3: pérdida por tramo de canal.

Aclaración obligatoria: entrenamiento con datos sintéticos; las métricas validan la simulación, no una finca real.

## 2:25–3:15 · Auditor de canales
Cambiar `indice_fuga_0_1` de un tramo y ejecutar de nuevo. Mostrar litros perdidos y `L recuperables / $1000 ARS`. Explicar que el tramo que más pierde no necesariamente es el primero que conviene reparar.

## 3:15–4:10 · Multiagente y control humano
Mostrar Arquitectura y, si hace falta, Decisión humana → Ver trazabilidad completa. El registro completo queda para etapas posteriores.
- Agente de Datos valida.
- Agente de Diagnóstico estima señales.
- Agente de Priorización propone orden/tiempos.
- Agente de Alertas/Registro conserva trazabilidad.

H1: aceptar/modificar/rechazar.
H2: compuertas manuales.
H3: evidencia insuficiente → inspección/criterio humano.

## 4:10–5:00 · Límites y siguiente paso
"La hipótesis del 15% todavía requiere medición de campo. Para pasar a un piloto real, reemplazamos el gemelo digital por sondas comerciales y caudalímetros; el software y el protocolo permanecen."

## Demo de respaldo
1. Escenario base → Simular.
2. Mostrar prioridad de sectores.
3. Mostrar Tramo recomendado para reparar.
4. Cambiar fuga del Tramo B.
5. Simular otra vez.
6. Registrar decisión H1 = Modificar.
7. Mostrar M8 actualizado.
