# Guía de Implementación: Gurobi Solver para Markowitz

## Estado Actual

El módulo `app/services/markowitz.py` es una **MAQUETA** sin funcionalidad real.
Retorna pesos iguales para ambas estrategias hasta que sea implementada.

## Instalación de Gurobi

### 1. Descargar Gurobi
- Ir a: https://www.gurobi.com/downloads/gurobi-software/
- Descargar versión para Windows
- Instalar en directorio (ej: `C:\gurobi1200`)

### 2. Obtener Licencia
- Gurobi requiere licencia (free para académicos/pequeños proyectos)
- Académica: https://www.gurobi.com/features/academic-named-user-license/
- Free Trial: 3 meses sin restricciones

### 3. Instalar paquete Python
```bash
pip install gurobipy
```

### 4. Configurar variables de entorno (Windows)
```powershell
$env:GUROBI_HOME = "C:\gurobi1200\win64"
$env:PATH = "$env:GUROBI_HOME\bin;$env:PATH"
```

## Estructura para Implementar

### compute_markowitz_portfolio (Max Sharpe)

```python
def compute_markowitz_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """Portafolio de máximo Sharpe ratio con Gurobi."""
    
    n = len(tickers)
    ann_returns = daily_returns.mean(axis=0) * 252
    ann_cov = np.cov(daily_returns.T) * 252
    
    # Crear modelo Gurobi
    model = gp.Model("Markowitz_MaxSharpe")
    
    # Decisión: pesos w[i] para cada activo
    w = model.addMVar(n, name="weights", lb=0.0, ub=1.0)
    
    # Restricción: suma de pesos = 1
    model.addConstr(w.sum() == 1.0)
    
    # Retorno esperado del portafolio
    port_return = ann_returns @ w
    
    # Volatilidad del portafolio
    # vol^2 = w^T * Cov * w
    variance = w @ ann_cov @ w
    
    # Sharpe Ratio = (return - rf) / vol
    # Maximizar Sharpe = Maximizar (return - rf) / vol
    
    # _IMPORTANTE_: Gurobi es lineal/cuadrático
    # Para max Sharpe, usar aproximación o reformulación cónica
    
    # Opción simplificada: max (return - rf) sujetado a vol <= target_vol
    target_vol = 0.15  # adaptar según dataset
    
    model.addConstr(variance <= target_vol**2)
    model.setObjective(port_return, GRB.MAXIMIZE)
    
    model.optimize()
    
    if model.status == GRB.OPTIMAL:
        weights = w.X
    else:
        weights = np.ones(n) / n  # fallback
    
    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)
```

### minimum_variance_portfolio

```python
def minimum_variance_portfolio(
    tickers: List[str],
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.05,
) -> Dict:
    """Portafolio de mínima varianza con Gurobi."""
    
    n = len(tickers)
    ann_cov = np.cov(daily_returns.T) * 252
    
    model = gp.Model("Markowitz_MinVar")
    
    w = model.addMVar(n, name="weights", lb=0.0, ub=1.0)
    model.addConstr(w.sum() == 1.0)
    
    variance = w @ ann_cov @ w
    model.setObjective(variance, GRB.MINIMIZE)
    
    model.optimize()
    
    if model.status == GRB.OPTIMAL:
        weights = w.X
    else:
        weights = np.ones(n) / n
    
    return _portfolio_stats(weights, daily_returns, risk_free_rate, tickers)
```

## Testing

```python
# test_gurobi.py
import numpy as np
from app.services.markowitz import compute_markowitz_portfolio

tickers = ["AAPL", "MSFT", "GOOGL"]
daily_returns = np.random.randn(252, 3)  # 1 año de datos

result = compute_markowitz_portfolio(tickers, daily_returns)
assert result['weights'].sum() == 1.0
assert all(w >= 0 for w in result['weights'])
print(f"Weights: {result['weights']}")
print(f"Sharpe: {result['sharpe_ratio']:.3f}")
```

## Notas Importantes

1. **Solver**: Gurobi puede resolver problemas cuadráticos (QP) y cónicos (SOCP)
2. **Max Sharpe**: Requiere reformulación cónica o aproximación lineal
3. **Performance**: Gurobi es muy rápido incluso para 100+ activos
4. **Licencia**: Validate antes de deploy

## Archivos a Actualizar

- `app/services/markowitz.py` - Main implementation
- `requirements.txt` - Agregar `gurobipy`
- Tests en `tests/test_portfolio.py`

---
**Responsables**: Grupo de Capstone
**Deadline**: Definir según planificación
