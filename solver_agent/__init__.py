"""
solver_agent/ -- Pipeline LLM supervisado para optimizacion de portafolios P4.

Arquitectura inspirada en OptiMUS (2402.10172) y OR-LLM-Agent (2503.10009):

  Manager   : claude-opus-4-6  -- orquesta el loop, decide estrategia
  Programador: claude-haiku-4-5 -- genera y repara codigo Gurobi/scipy
  Evaluador  : claude-opus-4-6  -- interpreta DiagnosticReport, da feedback

Flujo:
  Programador genera codigo
       |
       v
  SolverSandbox ejecuta  -->  DiagnosticReport
       |
       v
  Evaluador interpreta  -->  decision: accept | retry | abort
       |                         |
       |          retry: feedback estructurado al Programador
       |          accept: devuelve SolverResult al usuario
       v
  Manager decide si cambiar estrategia o abortar

Principio clave (OptiMUS):
  Cada agente recibe SOLO el contexto relevante para su tarea.
  El Manager mantiene el estado global; los sub-agentes trabajan modularmente.
"""

from .pipeline import P4Pipeline, PipelineResult
from .agents import ProgramadorAgent, EvaluadorAgent, ManagerAgent

__all__ = ["P4Pipeline", "PipelineResult", "ProgramadorAgent", "EvaluadorAgent", "ManagerAgent"]
