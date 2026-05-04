# Solver — Implementación Académica FinPUC

Implementación de referencia del modelo de optimización de portafolios FinPUC. Contiene la pipeline de notebooks secuencial y el módulo `markowitz_pipeline.py` que encapsula toda la lógica reutilizable. Los artefactos generados aquí alimentan el análisis offline; la webapp en `app/` reproduce los cálculos en tiempo de ejecución desde SQLite.

---

## Estructura

```
solver/
├── markowitz_pipeline.py          # Módulo central reutilizable por todos los notebooks
├── 01_Preparar_Datos.ipynb        # Carga de datos y construcción del universo F5
├── 02_Modelo_Markowitz.ipynb      # Optimización media-varianza por perfil
├── 03_Perfiles_Riesgo.ipynb       # Sub-universos por perfil de riesgo
├── 04_Resultados_Finales.ipynb    # Tablas comparativas finales
├── 05_Proyeccion_Valorizada.ipynb # Proyecciones forward valorizadas
├── comparable/
│   └── comparable.ipynb           # Benchmark de referencia (top-20 equiponderado)
└── outputs/                       # Artefactos pre-computados (no subir archivos .pkl grandes)
    ├── daily_returns.pkl          # Retornos diarios logarítmicos (universo F5 completo)
    ├── weekly_returns.pkl         # Retornos semanales totales (precio + dividendo)
    ├── estimation_returns.pkl     # Ventana de estimación limpia (416 semanas, sin COVID)
    ├── mu.pkl                     # Vector μ anualizado
    ├── sigma.pkl                  # Matriz Σ anualizada (con shrinkage)
    ├── universe_f5.csv            # Metadatos del universo F5
    ├── sector_summary.csv         # Resumen sectorial
    └── *.csv                      # Tablas de resultados por perfil
```

---

## Pipeline de ejecución

Los notebooks deben ejecutarse en orden. Cada uno persiste sus salidas en `outputs/` para que el siguiente las consuma.

```
01_Preparar_Datos
   ↓  universe_f5.csv, daily_returns.pkl, weekly_returns.pkl
02_Modelo_Markowitz
   ↓  estimation_returns.pkl, mu.pkl, sigma.pkl
03_Perfiles_Riesgo
   ↓  subuniverses_by_profile.csv
04_Resultados_Finales
   ↓  markowitz_profile_weights.csv, tabla_final_markowitz_vs_equiponderado.csv
05_Proyeccion_Valorizada
   ↓  proyecciones por escenario
```

Para ejecutar el pipeline completo desde Python:

```python
from markowitz_pipeline import run_all
run_all()
```

---

## Filtro F5 — Universo de Activos

El universo elegible aplica cinco filtros secuenciales antes de cualquier optimización:

| Filtro | Criterio | Valor umbral |
|--------|----------|--------------|
| F1: Historia mínima | Días de datos disponibles | ≥ 2 520 días (~10 años) |
| F2: Precio mínimo | Precio de cierre actual | ≥ USD 5.00 |
| F3: Capitalización bursátil | Market cap | ≥ USD 2 000 000 000 |
| F4: Volatilidad anualizada | Rango aceptable | 5% ≤ σ ≤ 100% |
| F5: Clasificación sectorial | Sector GICS conocido | Excluye "Unknown" y "Shell Companies" |

Resultado: ~1 165 tickers del dataset original de 1 406 pasan el filtro F5.

---

## Perfiles de Riesgo

Cinco perfiles FinPUC, cada uno con parámetros de optimización específicos:

| Perfil | Tolerancia pérdida (α_p) | Gamma (γ) | Peso máx. por activo | Candidatos sub-universo | Límite sectorial |
|--------|--------------------------|-----------|----------------------|-------------------------|------------------|
| Muy conservador | 0% | 60.0 | 5% | 40 | 30% |
| Conservador | 5% | 35.0 | 7% | 60 | 30% |
| Neutro | 15% | 18.0 | 10% | 80 | 25% |
| Arriesgado | 30% | 8.0 | 15% | 100 | 30% |
| Muy arriesgado | 40% | 4.0 | 20% | 120 | 35% |

**γ (gamma)**: parámetro de aversión al riesgo en la función de utilidad cuadrática. A mayor γ, mayor penalización a la varianza respecto al retorno esperado.

**α_p**: pérdida máxima tolerable en el escenario adverso. Es la restricción de validación; no entra directamente en la optimización Markowitz.

---

## Modelo Markowitz — Supuestos

### 1. Función objetivo

```
max  wᵀμ - ½ γ wᵀΣw
 w

s.t.  Σᵢ wᵢ = 1          (presupuesto total invertido)
      0 ≤ wᵢ ≤ wₘₐₓ      (sin ventas en corto; concentración máxima por perfil)
```

### 2. Supuestos estadísticos

**Distribución de retornos**
- Se supone que los retornos son **estacionarios e i.i.d.** dentro de la ventana de estimación.
- El modelo no captura autocorrelación ni heterocedasticidad (e.g., GARCH).

**Estimación de μ (retorno esperado)**
- Se calcula la media aritmética semanal y se anualiza multiplicando por 52.
- Alternativa de respaldo: CAGR empírico si la media semanal no está disponible.
- **Supuesto**: la media histórica es un estimador insesgado del retorno futuro esperado.

**Estimación de Σ (covarianza)**
- Covarianza muestral semanal anualizada (× 52).
- Regularización diagonal (*shrinkage* de Ledoit-Wolf simplificado):
  ```
  Σ_reg = 0.90 × Σ_muestral + 0.10 × diag(Σ_muestral)
  ```
- Recorte de valores propios negativos al mínimo `ε = 1e-8` para garantizar definición positiva.
- **Supuesto**: la estructura de correlación histórica persiste en el futuro.

### 3. Ventana de estimación

- **Longitud**: 8 años = 416 semanas (`ESTIMATION_YEARS = 8`).
- **Mínimo de observaciones válidas**: 350 semanas por activo (`MIN_VALID_WEEKS = 350`); activos con menos semanas son excluidos.
- **Exclusión del período COVID**: semanas entre 2020-01-01 y 2022-12-31 son eliminadas de la estimación para evitar que el régimen extremo de volatilidad distorsione los parámetros (referencia metodológica: Informe 1, Sección 2.2.2).
- **Supuesto**: el período 2020-2022 es un régimen atípico no representativo del comportamiento estructural de los activos.

### 4. Sin tasa libre de riesgo

- La optimización **no incluye una tasa libre de riesgo** (`r_f = 0`).
- El ratio de Sharpe se reporta como `μ_p / σ_p` sin descontar `r_f`.
- **Justificación**: alineación con el Informe 1 y con la comparación directa entre portafolios sin sesgo por elección de benchmark de renta fija.

### 5. Sin ventas en corto

- Todos los pesos están restringidos a `wᵢ ≥ 0`.
- **Supuesto**: el inversor retail bajo la regulación FinPUC no puede tomar posiciones cortas.

### 6. Mercados completos y liquidez perfecta

- Se supone que todos los activos del universo F5 son **perfectamente líquidos** y pueden adquirirse en cualquier proporción.
- No se modelan costos de impacto de mercado (*market impact*).
- Las comisiones de transacción son manejadas por la capa LP en `app/services/optimizer.py`, no en este solver.

### 7. Retornos totales (precio + dividendo)

- Los retornos semanales incluyen dividendos reinvertidos.
- **Supuesto**: el inversor reinvierte automáticamente todos los dividendos recibidos.

### 8. Horizonte de inversión

- El modelo calibra parámetros con frecuencia **semanal** y los anualiza.
- El horizonte implícito de evaluación de desempeño es **1 año**.
- **Supuesto**: la matriz de covarianza escala linealmente con el tiempo (movimiento browniano).

---

## Sub-universos por Perfil

Antes de la optimización, cada perfil selecciona su universo candidato mediante un *score* compuesto:

| Componente | Muy conservador | Conservador | Neutro | Arriesgado | Muy arriesgado |
|------------|:--------------:|:-----------:|:------:|:----------:|:--------------:|
| Market cap rank | 30% | 35% | 35% | 30% | 25% |
| Baja volatilidad rank | 35% | 35% | 15% | 10% | 5% |
| Sharpe ratio rank | — | 20% | 35% | 25% | 25% |
| Retorno rank | — | — | 15% | 35% | 45% |
| Bonus dividendo | 20% | 10% | — | — | — |
| Bonus sector defensivo | 15% | — | — | — | — |

**Pre-filtros adicionales**:
- *Muy conservador*: solo activos con volatilidad ≤ percentil 55 del universo F5.
- *Conservador*: solo activos con volatilidad ≤ percentil 70 del universo F5.
- Sectores defensivos: Utilities, Consumer Defensive, Healthcare.

---

## Benchmark: Equiponderado Top-20

Portafolio de referencia pasivo construido como:
- Los 20 activos de mayor market cap dentro del universo F5.
- Peso uniforme: `wᵢ = 1/20 = 5%` por activo.
- Evaluado sobre la misma ventana de estimación que Markowitz para comparabilidad directa.

---

## Solver numérico

- **Método**: `scipy.optimize.minimize` con método `SLSQP` (Sequential Least Squares Programming).
- **Tolerancia de convergencia**: `ftol = 1e-10`.
- **Iteraciones máximas**: 1 000.
- El problema es convexo (Σ definida positiva ⇒ solución única global).

---

## Parámetros globales

| Constante | Valor | Descripción |
|-----------|-------|-------------|
| `TRADING_DAYS_PER_YEAR` | 252 | Días hábiles por año |
| `WEEKS_PER_YEAR` | 52 | Semanas por año |
| `ESTIMATION_YEARS` | 8 | Años de la ventana de estimación |
| `MIN_VALID_WEEKS` | 350 | Semanas mínimas para incluir un activo |
| `SHRINKAGE_COVARIANCE` | 0.10 | Factor de shrinkage diagonal |
| `EPS_COV` | 1e-8 | Piso de valores propios para Σ |
| `DEFAULT_MAX_WEIGHT` | 0.40 | Peso máximo por defecto (override) |
| `EXCLUDE_START` | 2020-01-01 | Inicio período COVID excluido |
| `EXCLUDE_END` | 2022-12-31 | Fin período COVID excluido |

---

## Dependencias

```
numpy
pandas
scipy
```

Los notebooks requieren además `matplotlib` y `seaborn` para visualizaciones. No hay dependencia de Gurobi ni de ningún solver comercial.

---

## Referencias

- **Informe 1** — Define la estructura del modelo, valores de γ, restricciones y tablas de parámetros (Tablas 0.10, 2.1, 2.4; Secciones 2–4).
- Markowitz, H. (1952). *Portfolio Selection*. Journal of Finance, 7(1), 77–91.
- Ledoit, O. & Wolf, M. (2004). *A well-conditioned estimator for large-dimensional covariance matrices*. Journal of Multivariate Analysis, 88(2), 365–411.
