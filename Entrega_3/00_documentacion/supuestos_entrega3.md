# Supuestos — Entrega 3

## Generales

| Supuesto | Valor | Referencia |
|---|---|---|
| Capital inicial (C0) | $1,000 USD | Entrega 2 — Supuestos K1 |
| Horizonte de simulación | 260 semanas (5 años) | Entrega 2 — Supuestos K2 |
| Simulaciones por combinación | 5,000 | Entrega 2 — Supuestos K8 |
| Sensibilidad logística (s) | 20 | Entrega 2 — Supuestos K4 |
| Tasa libre de riesgo (Rf) | 2% anual | Entrega 2 — Supuestos F1 |
| Semillas deterministas | SHA-256 por combinación | Entrega 2 — Supuestos K11 |

## Notebook 01 — Sensibilidad de K%

| Supuesto | Valor |
|---|---|
| Valores de K evaluados | 0.25%, 0.5%, 0.75%, 1%, 1.5%, 2%, 3%, 5% |
| Metodologías evaluadas | Equiponderado, Markowitz, MinVar, BL Momentum Top20 6M |
| Perfiles evaluados | Los 5 perfiles (muy_conservador a muy_arriesgado) |
| Turnover por recomendación | 5% de la riqueza actual |
| Comisión sobre turnover | K% del 5% de la riqueza |
| Comisión inicial | K% sobre C0 (una sola vez) |
| Retornos semanales | Normales i.i.d. con media y volatilidad de KPIs Entrega 2 |
| Escenario proyectado | Neutro (sin shift ±0.5σ) |

## Notebook 02 — Optimización de λ

| Supuesto | Valor |
|---|---|
| Valores de λ evaluados | 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 |
| K utilizado | Valor óptimo del notebook 01 |
| f1(w) | Retorno esperado anualizado del portafolio (wᵀμ) |
| f2(w) | Utilidad FinPUC ∝ K · P₂(return) · (1−P₁(loss)) |
| Normalización de f1 y f2 | Min-max scaling al rango [0,1] antes de combinar |
| Metodología utilizada | La de mejor Score P4 del notebook 01 |
| P1 y P2 | Funciones logísticas con s=20, mismas que Entrega 2 |
| P1 activación | Solo si pérdida > tolerancia del perfil |

## Limitaciones

- Los KPIs de retorno/volatilidad son fijos (provienen de la Entrega 2) — no se re-optimizan para cada K o λ
- La distribución normal subestima eventos de cola
- El turnover del 5% es un supuesto no calibrado con datos reales
- λ se evalúa en grilla discreta (11 puntos) — el óptimo real podría estar entre dos valores
- K y λ se optimizan secuencialmente (primero K, luego λ) — una optimización conjunta podría dar un resultado distinto
