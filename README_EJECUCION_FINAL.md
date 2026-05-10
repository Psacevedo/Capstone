# Ejecucion final - Entrega 2

La carpeta funcional principal es:

`Implementacion caso benchmark teorico` (en Windows aparece con tildes).

## Notebooks finales

Ejecutar en este orden:

1. `Implementacion caso benchmark teorico/01_markowitz_vs_benchmark/markowitz_vs_benchmark_rebalanceo_pandemia.ipynb`
2. `Implementacion caso benchmark teorico/02_black_litterman/black_litterman.ipynb`
3. `Implementacion caso benchmark teorico/03_p4_montecarlo/p4_montecarlo_recomendador_portafolios.ipynb`

Cada notebook tiene su propia carpeta `outputs/`.

## Estado validado

- Markowitz vs Benchmark: ejecutado completo desde su carpeta nueva.
- Black-Litterman: ejecutado desde su carpeta nueva con 4 views centrales: `momentum`, `desempleo`, `momentum_top20_6m` y `momentum_top20_bottom20_1y`.
- Nueva tecnica Black-Litterman 6M: `momentum_top20_6m` usa las 20 mayores capitalizaciones disponibles para armar una view long 10 / short 10 por momentum semestral de 126 dias habiles y mantiene la optimizacion sobre el universo completo.
- Nueva tecnica Black-Litterman 1Y: `momentum_top20_bottom20_1y` usa las 40 mayores capitalizaciones disponibles para armar una view long 20 / short 20 por momentum anual de 252 dias habiles y mantiene la optimizacion sobre el universo completo.
- P4 Monte Carlo: ejecutado completo desde su carpeta nueva, comparando 6 tecnicas: Equiponderado, Markowitz, BL Momentum, BL Desempleo, BL Momentum Top20 6M y BL Momentum Top20-Bottom20 1Y.
- No quedan archivos `.py` en `Entrega 2`; el codigo necesario de Markowitz esta embebido dentro de los notebooks que lo usan.
- No quedan notebooks extra: solo existen los 3 `.ipynb` finales.

## Flags utiles

- `BL_FORCE_RECOMPUTE=1`: fuerza a recalcular las optimizaciones CVXPY centrales de Black-Litterman aunque existan outputs.
- `BL_RUN_CENTRAL_ANALYSIS=0`: permite abrir/validar el notebook Black-Litterman sin ejecutar el experimento central.
- `BL_RUN_VALIDATION_ANALYSIS=1`: activa validaciones adicionales de splits aleatorios y robustez en Black-Litterman.

## Estructura relevante

- `Implementacion caso benchmark teorico/00_documentacion`: PDFs y notas de apoyo del caso.
- `Implementacion caso benchmark teorico/01_markowitz_vs_benchmark`: notebook Markowitz y sus outputs.
- `Implementacion caso benchmark teorico/02_black_litterman`: notebook Black-Litterman y sus outputs.
- `Implementacion caso benchmark teorico/03_p4_montecarlo`: notebook P4 Monte Carlo y sus outputs.
- `Historical_Stocks_filtrado_sin_pandemia`: datos requeridos por los notebooks.
- `Implementacion multiples slipts` e `IMPLEMENTACION OFICIAL`: outputs auxiliares usados por las validaciones.
- `02_datos_originales`: ZIP original de datos.
