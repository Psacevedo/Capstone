# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the webapp locally (Docker required)
docker compose up --build
# Custom port
FINPUC_PORT=8081 docker compose up --build
```

## Architecture

### Webapp (`app/`)
FastAPI SPA served at `/`. On startup, builds a SQLite DB from the CSV files if it doesn't exist yet. After that, all reads go to SQLite.

- `config.py` — Central config: `DATA_DIR` and `DB_PATH` read from env vars (defaults: `/data/Historical_Stocks`, `/data/finpuc_cache.db`)
- `db.py` — DB schema (`stocks`, `prices` tables) and `build_db_if_needed()`; background build on first startup
- `routers/portfolio.py` — Main endpoint `/api/portfolio/recommend`; orchestrates F5 filtering, Markowitz optimization, CVaR, scenarios, and client simulation
- `routers/report.py` — PDF report generation from `Informe/`
- `routers/sectors.py`, `routers/stocks.py` — Universe explorer endpoints
- `services/markowitz.py` — Markowitz, min-variance, max-return, CVaR, and efficient frontier computations
- `services/optimizer.py` — `ScipyPortfolioSolver`: LP solver (scipy/HiGHS); supports commissions and 2-stage stochastic LP
- `services/portfolio_validator.py` — `PortfolioValidator`: validates budget, non-negativity, and loss-tolerance constraints against the 5 FinPUC risk profiles
- `services/universe_f5.py` — F5 filter logic (min history, min price, market cap, volatility, sector quality)
- `services/simulation.py` — Monthly client simulation with commissions and drawdown exit
- `services/scenarios.py` — Favorable/neutral/adverse scenario projections
- `services/methodology_catalog.py` — Academic catalog of methodology parameters, linked to report sections (e.g. `"Tabla 2.1 / Seccion 2.2.2"`)

### Solver (`solver/`)
Academic implementation of the FinPUC optimization model. Sequential notebook pipeline aligned with Informe 1:

1. `01_Preparar_Datos.ipynb` — Data preparation and F5 filtering
2. `02_Modelo_Markowitz.ipynb` — Markowitz mean-variance implementation
3. `03_Perfiles_Riesgo.ipynb` — Risk profile sub-universe analysis
4. `04_Resultados_Finales.ipynb` — Final results and summary tables
- `markowitz_pipeline.py` — Reference offline implementation (profile-specific γ, sub-universe scoring)
- `comparable/comparable.ipynb` — Benchmark comparison (top-20 equal-weight)
- `outputs/` — Pre-computed artifacts: `mu.pkl`, `sigma.pkl`, `daily_returns.pkl`, and `.csv` summaries

### Data
- `Data/Historical_Stocks/` — 1,406 CSV files (`stock_return_<TICKER>.csv`) + `stocks_info.txt` (metadata in `TICKER;{dict}` format). Not in Docker image; mounted as a volume.
- 1,165 tickers with valid data; date range ~1973–2026; 11 GICS sectors.

### Risk Profiles
Five FinPUC profiles map to loss tolerance `alpha_p` (defined in `services/portfolio_validator.py`):
| Profile | α_p |
|---|---|
| muy_conservador | 0% |
| conservador | 5% |
| neutro | 15% |
| arriesgado | 30% |
| muy_arriesgado | 40% |

## Key Implementation Notes

- **LP solver**: `app/services/optimizer.py` (`ScipyPortfolioSolver`) uses `scipy.optimize.linprog` (HiGHS backend). No Gurobi dependency.
- **DB build is idempotent**: runs once in background on startup. Deleting the Docker volume forces a rebuild.
- **Methodology catalog parameters** reference report sections directly (e.g. `"report_reference": "Tabla 2.1 / Seccion 2.2.2"`) — keep these aligned with `Informe/`.
- **`solver/outputs/` artifacts** (`.pkl` files for `mu`, `sigma`, return matrices) are produced by the notebooks for offline analysis; the webapp's `services/markowitz.py` computes these at runtime from SQLite.
