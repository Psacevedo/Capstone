# Resumen ejecutivo — Entrega 3

## Objetivo

Determinar dos parámetros clave del modelo de negocio de FinPUC:

1. **K% (comisión)**: ¿Cuánto puede cobrar FinPUC sin que los clientes se retiren masivamente?
2. **λ (balance multiobjetivo)**: ¿Cómo ponderar el retorno del cliente vs la utilidad de la empresa?

## Método

### Notebook 01 — Sensibilidad de K%
- Se simulan 8 valores de comisión: K ∈ {0.25%, 0.5%, 0.75%, 1%, 1.5%, 2%, 3%, 5%}
- Para cada K, se ejecuta Monte Carlo (5,000 trayectorias × 260 semanas × 5 perfiles × 4 metodologías)
- Se mide: riqueza terminal, tasa de retiro, utilidad FinPUC, Score P4
- Se identifica el K que maximiza el Score P4

### Notebook 02 — Optimización de λ
- Se evalúan 11 valores de λ ∈ {0, 0.1, 0.2, ..., 1.0}
- Para cada λ, se resuelve `max λ·f1(w) + (1−λ)·f2(w)` con el K óptimo del notebook 01
- f1(w) = retorno esperado del cliente (wᵀμ_BL)
- f2(w) = utilidad FinPUC ∝ K · P₂ · (1−P₁)
- Se construye la frontera de Pareto cliente vs empresa

## Resultados clave

*(Se completan tras ejecutar los notebooks)*

| Parámetro | Valor óptimo | Score P4 | Interpretación |
|---|---|---|---|
| K óptimo | *(del notebook 01)* | — | % que maximiza Score P4 |
| λ óptimo | *(del notebook 02)* | — | Balance cliente vs empresa |

## Recomendación final

*(Se completa tras ejecutar los notebooks)*

La combinación óptima K% + λ + metodología + perfil se documenta en `03_resultados_finales/conclusiones_entrega3.md`.
