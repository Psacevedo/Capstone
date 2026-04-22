# P4 FinPUC

Sistema recomendador de portafolios desarrollado para el proyecto capstone P4 de la PUC Chile.
La aplicacion combina un explorador del universo F5 con un flujo principal de recomendacion,
escenarios y simulacion del cliente.

## Capacidades principales

- Recomendacion automatica por perfil de riesgo con 5 perfiles FinPUC.
- Filtros del universo F5: historia minima, precio minimo, market cap, volatilidad y calidad sectorial.
- Motor base honesto con la implementacion actual: media-varianza / minima varianza / maximo retorno + CVaR + escenarios + simulacion cliente.
- Escenarios favorable, neutro y desfavorable para revisar capital proyectado.
- Simulacion semanal del cliente con aceptacion simplificada, comisiones y retiro por drawdown.
- Exploracion por sector del universo operativo con metricas historicas por accion.

## Estructura del producto

- `Universo F5`: exploracion de sectores y acciones disponibles.
- `Sistema FinPUC > Recomendacion`: flujo principal para perfilar y optimizar.
- `Sistema FinPUC > Escenarios`: proyeccion de capital del portafolio recomendado.
- `Sistema FinPUC > Simulacion cliente`: dinamica semanal simplificada del sistema.
- `Sistema FinPUC > Metodologia`: explicacion tecnica y limites de la version actual.

## Stack

- Backend: Python 3.11, FastAPI, Uvicorn
- Base de datos: SQLite local
- Frontend: HTML, CSS, Vanilla JS, Plotly
- Contenedores: Docker, Docker Compose

## Ejecucion local

```bash
docker compose up --build
```

La app queda disponible en `http://localhost:8080`.
El servicio principal de Compose es `finpuc` y la cache SQLite persiste en el volumen `finpuc_cache`.
Si `8080` ya esta ocupado, puedes levantarla en otro puerto con `FINPUC_PORT=8081 docker compose up --build`.

## Datos esperados

El contenedor monta los historicos desde `./Data/Historical_Stocks`.
En el primer arranque se construye la cache SQLite y luego las lecturas son directas.
La imagen empaqueta la app consolidada en la raiz y el informe (`Informe/`) para mantener trazabilidad en "Datos y referencias"; `webapp/` y `Data/` quedan fuera del build mediante `.dockerignore`.

## Estado metodologico

- Implementado: perfiles FinPUC, filtros F5, constructor por perfil, CVaR historico, escenarios y simulacion del cliente.
- No implementado aun: Black-Litterman (`mu_BL`, `tau`, `Omega`, `views`) y la escalarizacion final multiobjetivo con `lambda`.

## Contexto academico

Proyecto capstone del programa ICI + TI de la Pontificia Universidad Catolica de Chile.
