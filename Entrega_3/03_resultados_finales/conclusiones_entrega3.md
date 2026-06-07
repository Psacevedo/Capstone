# Conclusiones — Entrega 3

## Resumen de hallazgos

### Notebook 01 — Sensibilidad de K%

**K óptimo**: *(se completa tras ejecutar el notebook 01)*

| K evaluado | Score P4 promedio | Riqueza media | Utilidad media | Retiro medio |
|---|---|---|---|---|
| *(del CSV)* | | | | |

**Interpretación**:
- K bajos favorecen al cliente (más riqueza terminal, menos retiro)
- K altos generan más utilidad inmediata pero disparan la tasa de retiro
- El K óptimo balancea ambos efectos maximizando el Score P4

### Notebook 02 — Optimización de λ

**λ óptimo (Score P4)**: *(se completa tras ejecutar el notebook 02)*
**λ óptimo (Score ponderado)**: *(se completa tras ejecutar el notebook 02)*

| λ evaluado | Score P4 | Score ponderado | Riqueza | Utilidad |
|---|---|---|---|---|
| *(del CSV)* | | | | |

**Interpretación**:
- λ = 0.0 → FinPUC solo optimiza su utilidad
- λ = 1.0 → FinPUC solo optimiza el retorno del cliente
- El λ óptimo encontrado representa el mejor balance según los datos

### Recomendación final para FinPUC

| Parámetro | Valor óptimo |
|---|---|
| **K (comisión)** | *(del notebook 01)* |
| **λ (balance)** | *(del notebook 02)* |
| **Metodología** | *(mejor combinación)* |
| **Perfil** | *(mejor combinación)* |
| **Score P4 esperado** | *(mejor combinación)* |

### Comparación con Entrega 2

La Entrega 2 usaba K = 1% fijo y un Score P4 sin parámetro λ explícito.
La Entrega 3 demuestra que:

1. El K óptimo puede ser distinto al 1% asumido
2. El λ permite calibrar explícitamente la prioridad entre cliente y empresa
3. La combinación K + λ óptimos puede mejorar el Score P4 respecto a los defaults de la Entrega 2

### Limitaciones

- KPIs de retorno/volatilidad fijos (no se re-optimizan para cada K o λ)
- Distribución normal subestima eventos extremos
- Turnover del 5% es un supuesto
- λ evaluado en grilla discreta (11 puntos)
- K y λ optimizados secuencialmente, no conjuntamente
