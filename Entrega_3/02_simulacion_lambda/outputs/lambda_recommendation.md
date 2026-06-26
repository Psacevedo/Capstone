# Recomendación de λ — Optimización multiobjetivo

## λ óptimo (Score P4): **0.7**

Este λ maximiza el Score P4 estándar sobre todas las combinaciones.

## λ óptimo (Score ponderado): **0.0**

Este λ maximiza el score escalarizado λ·f1 + (1−λ)·f2.

## Mejor combinación individual

- **λ**: 0.5
- **K**: 5.0%
- **Perfil**: muy_arriesgado
- **Metodología**: Markowitz
- **Score P4**: 3026.29
- **Riqueza terminal**: \$2,977.84
- **Tasa de retiro**: 4.7%
- **Utilidad FinPUC**: \$95.45

## Interpretación

- λ = 0 → FinPUC solo optimiza su utilidad (ignora al cliente)
- λ = 1 → FinPUC solo optimiza el retorno del cliente (ignora su utilidad)
- λ intermedio → balance entre ambos objetivos
- El Score P4 ya incorpora un balance implícito (riqueza + utilidad − penalización)

## Recomendación final

Usar λ = 0.7 con K = 5.0% para el recomendador FinPUC.
La metodología óptima es Markowitz en perfil muy_arriesgado.
