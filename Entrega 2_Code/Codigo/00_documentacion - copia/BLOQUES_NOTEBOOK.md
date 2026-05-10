# Estructura del Notebook - Bloques Validables

## Para DESACTIVAR todos los logs:
Cambiar en BLOQUE 0:
```python
DEBUG = False  # Cambiar de True a False
```

## BLOQUE 0: Setup (Ya configurado)
- Paths
- Logging function
- Constantes

## BLOQUE 1: Carga script base (Ya configurado)
- load_script_module()
- Extrae funciones
- Valida que funciones existan

## BLOQUE 2: Parametros (Ya configurado)
- Define constantes del experimento
- Imprime para validar

## BLOQUE 3: Definir clases y funciones (PROXIMO)
```python
@dataclass(frozen=True)
class ScenarioDataset:
    ...

def load_returns_from_directory():
    ...

def load_scenario_dataset():
    ...

def rebalance_windows():
    ...

def training_view():
    ...

def solve_snapshot_portfolios():
    ...

def evaluate_rebalanced_window():
    ...
```

## BLOQUE 4: Cargar datasets sin y con pandemia (PROXIMO)
```python
log("Cargando sin_pandemia...")
sin_dataset = load_scenario_dataset("sin_pandemia", MARKET_SIZE)
log(f"Shape: {sin_dataset.returns.shape}")

log("Cargando con_pandemia...")
con_dataset = load_scenario_dataset("con_pandemia", MARKET_SIZE)
log(f"Shape: {con_dataset.returns.shape}")
```

## BLOQUE 5: Ejecutar experimento h7_f2 (PROXIMO)
```python
all_results = {}
for scenario_key, dataset in [("sin_pandemia", sin_dataset), ("con_pandemia", con_dataset)]:
    log(f"Procesando {scenario_key}...")
    segment_df, rebalance_df, summary_df, frontier_df = evaluate_rebalanced_window(...)
    all_results[scenario_key] = {...}
    log(f"OK: {len(rebalance_df)} portafolios")
```

## BLOQUE 6: Exportar a CSV (PROXIMO)
```python
log("Exportando CSVs...")
# Crear DataFrames
# Guardar archivos
# Log cada archivo
```

## BLOQUE 7: Comparar escenarios (PROXIMO)
```python
log("Comparando sin vs con pandemia...")
# Crear comparison DataFrame
# Guardar CSV
# Imprimir tabla
```

## BLOQUE 8: Gráficas (PROXIMO)
- Gráfica 1: 4 subgráficas (Sharpe, Retorno, Delta, Drawdown)
- Gráfica 2: Ranking Sharpe
- Gráfica 3: Frontera coloreada
- Gráfica 4-5: Heatmaps

Cada gráfica con:
```python
try:
    log("Creando grafica X...")
    fig, ax = ...
    log("  - Ploteo OK")
    plt.savefig(...)
    log(f"  - Guardado OK: {filename}")
    plt.show()
except Exception as e:
    log(f"ERROR en grafica X: {e}", "ERROR")
```

## NOTAS IMPORTANTES:
- Cada BLOQUE es independiente
- Si un BLOQUE falla, puedes debuggear solo ese
- Los logs te muestran exactamente dónde falló
- Para eliminar todos los logs: solo DEBUG = False
