# Mapa del MVP — Etapa Lozano

## Flujo principal

```text
Clima + datos de 1–10 sectores
              ↓
Normalización → gemelo digital horario
              ↓
Agente de Datos → Random Forest con sensor o proxy
              ↓
Diagnóstico → Priorización por reglas
              ↓
Revisión y decisión humana → registro temporal existente
```

## Canales

```text
Cuatro tramos + clima + caudal local
              ↓
Random Forest → porcentaje de pérdida
              ↓
Balance secuencial de litros
              ↓
Recuperación supuesta / costo → ranking → humano
```

## Módulos

- `app.py`: componentes y callbacks Gradio.
- `core/simulation.py`: orquestación, límites globales, agregar/eliminar.
- `core/sensors.py`: balance horario y ruido reproducible; sin Gradio ni hardware.
- `core/synthetic_data.py`: CSV, presets y generación de datasets sintéticos.
- `core/ai_models.py`: tres Random Forest entrenados al iniciar y métricas.
- `core/agents.py`: normalización, calidad, diagnóstico, reglas de prioridad y auditor de canales.
- `core/visuals.py`: gráficos, resumen y diagramas.
- `core/farm.py`: geometría relativa, IDs de canal y persistencia local de configuración.
- `core/farm_map.py`: SVG del croquis y cruce descriptivo de riesgo/pérdidas, sin alterar el ML.
- `core/decision.py`: H1 y protocolo temporal conservados del MVP.
- `assets/dashboard.css`: presentación, estados y móvil.

## Estado de sesión

Gradio mantiene sectores, escenario y resultado por sesión. La ficha se aplica al simular; agregar/eliminar/presets recalculan resultados. Editar invalida cifras anteriores. Los CSV son el escenario inicial y no se sobrescriben. GUARDAR CONFIGURACIÓN escribe `data/finca_config.json`; CARGAR valida y recalcula con el clima actual. Mover/cambiar canal da una vista previa hasta aplicar. La geometría no es una feature de los modelos.

## Frontera IA / reglas / humano

**IA:** riesgo y pérdida porcentual. **Simulación:** lecturas virtuales. **Cálculos:** volúmenes y eficiencia. **Reglas:** confianza por calidad, prioridad y agua/costo. **Humano:** decisión final y compuertas manuales.

La arquitectura futura sensor físico → gateway → API → IA → dashboard se muestra como propuesta. No está implementada. Trazabilidad persistente, evaluación avanzada y entrega final corresponden a las etapas siguientes.
