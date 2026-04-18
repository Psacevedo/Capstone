"""
solver/ — Sandbox supervisado de ejecución para el optimizador de portafolios P4.

Módulos:
  sandbox.py      — Ejecutor seguro con timeout y diagnóstico
  diagnostics.py  — Clasificación de estados del solver
  validators.py   — Validación de soluciones de portafolio
  fallback.py     — Solver de respaldo (scipy) cuando Gurobi no disponible
  models/         — Modelos LP prearmados para P4
"""

from .sandbox import SolverSandbox, SolverResult, SolverStatus
from .diagnostics import Diagnostics
from .validators import PortfolioValidator

__all__ = ["SolverSandbox", "SolverResult", "SolverStatus", "Diagnostics", "PortfolioValidator"]
