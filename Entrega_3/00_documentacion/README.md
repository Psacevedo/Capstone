# Entrega 3 — Simulación de K% y optimización multiobjetivo (λ)

## Estado del proyecto

**Fecha**: Junio 2026
**Equipo**: G13 — FinPUC
**Objetivo**: Determinar la comisión óptima K% y el parámetro de balance λ para el recomendador FinPUC.

## Estructura

```
Entrega_3/
├── 00_documentacion/
│   ├── README.md                    ← Este archivo
│   ├── resumen_ejecutivo.md         ← Resultados clave
│   ├── supuestos_entrega3.md        ← Supuestos de esta entrega
│   └── outputs/                     ← Gráficos y CSVs consolidados
│
├── 01_simulacion_k/
│   ├── simulacion_comisiones_k.ipynb   ← Notebook: sensibilidad de K%
│   └── outputs/                        ← CSVs y PNGs generados
│
├── 02_simulacion_lambda/
│   ├── simulacion_lambda_multiobjetivo.ipynb  ← Notebook: optimización de λ
│   └── outputs/                               ← CSVs y PNGs generados
│
├── 03_resultados_finales/
│   └── conclusiones_entrega3.md      ← Conclusiones y ranking final
│
└── entrega_1/
    └── Informe 1 - G13 (3).pdf       ← Referencia
```

## Notebooks — orden de ejecución

1. `01_simulacion_k/simulacion_comisiones_k.ipynb` — Sensibilidad de K%
2. `02_simulacion_lambda/simulacion_lambda_multiobjetivo.ipynb` — Optimización de λ

## Insumos requeridos

Los notebooks usan los KPIs generados por los notebooks de la Entrega 2:
- `../Entrega_2/01_markowitz_vs_benchmark/outputs/`
- `../Entrega_2/02_black_litterman/outputs/`
- `../Entrega_2/03_p4_montecarlo/outputs/`

## Requisitos de entorno

- Python 3.11
- numpy, pandas, matplotlib, scipy
- jupyterlab
- hashlib (stdlib)
- json (stdlib)

## Outputs esperados

| Archivo | Notebook | Contenido |
|---|---|---|
| `k_sensitivity_summary.csv` | 01 | Métricas por valor de K (riqueza, retiro, utilidad, Score P4) |
| `k_optimal_recommendation.md` | 01 | K óptimo recomendado |
| `lambda_pareto_frontier.csv` | 02 | Frontera de Pareto cliente vs empresa |
| `lambda_optimal_summary.csv` | 02 | Métricas por valor de λ |
| `lambda_recommendation.md` | 02 | λ óptimo recomendado |
| `ranking_final_recomendador.csv` | 03 | Ranking final con K y λ óptimos |
