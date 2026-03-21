# FinPUC Stock Explorer

Dashboard web para visualización y análisis de acciones del mercado estadounidense, organizado por sectores GICS. Desarrollado como parte del proyecto capstone P4 — PUC Chile.

## Características

- **1.400+ acciones** organizadas por sector (Technology, Financial Services, Healthcare, etc.)
- **Gráficos interactivos** de precios históricos, retornos y volatilidad por acción
- **Tabla paginada** (100 acciones por página) con filtro de búsqueda y ordenamiento por columna
- **Métricas financieras**: CAGR, volatilidad anualizada, Beta, P/E, Dividend Yield, Market Cap
- **Carga incremental**: base de datos SQLite en caché — el primer arranque procesa los CSVs, los siguientes son instantáneos
- Desplegado como contenedor Docker (FastAPI + Uvicorn + SQLite)

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (incluye Docker Compose)
- Los archivos de datos históricos (ver [`data/Historical_Stocks/README_DATA.md`](data/Historical_Stocks/README_DATA.md))

## Instalación rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/<tu-usuario>/finpuc-stock-explorer.git
cd finpuc-stock-explorer

# 2. Colocar los datos en la carpeta correcta
#    Ver data/Historical_Stocks/README_DATA.md para el formato esperado
cp /ruta/a/tus/datos/*.csv data/Historical_Stocks/
cp /ruta/a/tus/datos/stocks_info.txt data/Historical_Stocks/

# 3. Levantar el contenedor
docker compose up --build -d

# 4. Abrir en el navegador
#    http://localhost:8080
```

> **Primera vez:** el contenedor procesa ~1.400 CSVs y construye la caché SQLite.
> Esto tarda 3–5 minutos. La pantalla de carga muestra el progreso en tiempo real.
> Las siguientes veces arranca en segundos.

## Estructura del proyecto

```
finpuc-stock-explorer/
├── app/
│   ├── main.py          ← Aplicación FastAPI, endpoints y startup
│   ├── config.py        ← Variables de entorno y lista de sectores
│   ├── db.py            ← Construcción y consultas a SQLite
│   ├── routers/         ← Rutas de la API REST
│   ├── services/        ← Lógica de negocio (carga de CSVs, métricas)
│   └── templates/       ← HTML base (Jinja2)
├── static/
│   └── app.js           ← SPA vanilla JS (routing, render, charts)
├── data/
│   └── Historical_Stocks/
│       ├── .gitkeep
│       └── README_DATA.md  ← Formato y ubicación esperada de los datos
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## API endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/sectors` | Lista de sectores con conteo de acciones |
| `GET` | `/api/sectors/{sector}/stocks` | Acciones de un sector con métricas |
| `GET` | `/api/stocks/{ticker}` | Detalle completo de una acción |
| `GET` | `/api/stocks/{ticker}/history` | Serie histórica de precios |
| `GET` | `/api/status` | Estado de la carga inicial |

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Base de datos | SQLite (caché local) |
| Frontend | Vanilla JS, Chart.js |
| Contenedor | Docker, Docker Compose |

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DATA_DIR` | `/data/Historical_Stocks` | Ruta a los CSVs históricos |
| `DB_PATH` | `/data/webapp_cache.db` | Ruta de la base de datos SQLite |

## Contexto académico

Proyecto capstone del programa ICI + TI — Pontificia Universidad Católica de Chile.
Supervisor: Prof. Agustín Chiu.
