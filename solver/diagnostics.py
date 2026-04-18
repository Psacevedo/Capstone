"""
diagnostics.py — Clasificación y mapeo de códigos de estado del solver.

Cubre Gurobi (OptimizationStatus), scipy (status int) y errores de código.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class SolverStatus(Enum):
    """Estado final de una ejecución del solver."""
    OPTIMAL        = "optimal"        # Solución óptima encontrada
    INFEASIBLE     = "infeasible"     # No existe solución factible
    UNBOUNDED      = "unbounded"      # Objetivo no acotado
    INF_OR_UNBD    = "inf_or_unbd"   # Infactible o no acotado (sin pre-solve)
    TIME_LIMIT     = "time_limit"     # Se agotó el tiempo sin solución óptima
    TIME_LIMIT_SOL = "time_limit_sol" # Se agotó el tiempo, solución subóptima disponible
    TRIVIAL        = "trivial"        # Solución trivial (todos ceros o todo en caja chica)
    LICENSE_ERROR  = "license_error"  # Licencia Gurobi inválida o vencida
    CODE_ERROR     = "code_error"     # Error en el código generado por LLM
    RUNTIME_ERROR  = "runtime_error"  # Error de ejecución no relacionado al solver
    UNKNOWN        = "unknown"        # Estado no reconocido


# Mapa: código Gurobi OptimizationStatus → SolverStatus
GUROBI_STATUS_MAP: Dict[int, SolverStatus] = {
    1: SolverStatus.UNKNOWN,           # LOADED
    2: SolverStatus.OPTIMAL,           # OPTIMAL
    3: SolverStatus.INFEASIBLE,        # INFEASIBLE
    4: SolverStatus.INF_OR_UNBD,       # INF_OR_UNBD
    5: SolverStatus.UNBOUNDED,         # UNBOUNDED
    6: SolverStatus.UNKNOWN,           # CUTOFF
    7: SolverStatus.TIME_LIMIT_SOL,    # ITERATION_LIMIT (sol encontrada)
    8: SolverStatus.UNKNOWN,           # NODE_LIMIT
    9: SolverStatus.TIME_LIMIT,        # TIME_LIMIT sin solución
    10: SolverStatus.TIME_LIMIT_SOL,   # SOLUTION_LIMIT
    11: SolverStatus.UNKNOWN,          # INTERRUPTED
    12: SolverStatus.UNKNOWN,          # NUMERIC
    13: SolverStatus.UNKNOWN,          # SUBOPTIMAL
    14: SolverStatus.UNKNOWN,          # INPROGRESS
    15: SolverStatus.UNKNOWN,          # USER_OBJ_LIMIT
    16: SolverStatus.TIME_LIMIT_SOL,   # WORK_LIMIT con solución
    17: SolverStatus.UNKNOWN,          # MEM_LIMIT
}

# Mapa: scipy status int → SolverStatus
SCIPY_STATUS_MAP: Dict[int, SolverStatus] = {
    0: SolverStatus.OPTIMAL,
    1: SolverStatus.TIME_LIMIT,     # iteration limit
    2: SolverStatus.INFEASIBLE,
    3: SolverStatus.UNBOUNDED,
    4: SolverStatus.UNKNOWN,        # numerical difficulties
}

# Mensajes de diagnóstico para el agente Evaluador
DIAGNOSTICS_MSG: Dict[SolverStatus, str] = {
    SolverStatus.OPTIMAL: (
        "Solución óptima encontrada. Verificar factibilidad de restricciones y "
        "coherencia de pesos del portafolio."
    ),
    SolverStatus.INFEASIBLE: (
        "El modelo es infactible. Causas comunes: (1) tolerancia de pérdida α "
        "demasiado estricta para el escenario desfavorable; (2) restricción presupuesto "
        "Σwᵢ=1 incompatible con restricciones adicionales; "
        "(3) bounds negativos en variables de peso."
    ),
    SolverStatus.UNBOUNDED: (
        "El objetivo no está acotado. Verificar: (1) que las variables de peso tengan "
        "cota superior (wᵢ ≤ 1); (2) que no falte la restricción presupuesto Σwᵢ=1."
    ),
    SolverStatus.INF_OR_UNBD: (
        "Infactible o no acotado. Activar presolve (Presolve=1) para obtener diagnóstico "
        "más específico: m.Params.Presolve = 1."
    ),
    SolverStatus.TIME_LIMIT: (
        "Tiempo límite agotado sin solución factible. Acciones: (1) aumentar TimeLimit; "
        "(2) reducir el número de variables (sub-universo más pequeño); "
        "(3) relajar restricciones no críticas."
    ),
    SolverStatus.TIME_LIMIT_SOL: (
        "Tiempo límite agotado pero existe solución subóptima. Se puede usar esta solución "
        "o aumentar TimeLimit para buscar mejor solución."
    ),
    SolverStatus.TRIVIAL: (
        "Solución trivial detectada: el solver colocó todo o casi todo en caja chica. "
        "Verificar que la restricción de tolerancia α permita tomar posiciones en acciones "
        "con retorno positivo esperado."
    ),
    SolverStatus.LICENSE_ERROR: (
        "Error de licencia Gurobi. Verificar: (1) GUROBI_HOME apunta a la instalación "
        "correcta; (2) gurobi.lic está en ~/gurobi.lic o GRB_LICENSE_FILE apuntando "
        "al archivo; (3) la licencia no ha vencido. "
        "Licencia académica gratuita en: https://www.gurobi.com/academia/academic-program-and-licenses/"
    ),
    SolverStatus.CODE_ERROR: (
        "Error en el código generado. El traceback contiene la ubicación exacta del error. "
        "Revisar: imports, nombres de variables, tipos de datos, y sintaxis de gurobipy."
    ),
    SolverStatus.RUNTIME_ERROR: (
        "Error de ejecución no relacionado al solver. Verificar datos de entrada "
        "(NaN, arrays vacíos, tipos incorrectos)."
    ),
    SolverStatus.UNKNOWN: (
        "Estado desconocido. Revisar logs completos del solver."
    ),
}


@dataclass
class DiagnosticReport:
    """Reporte estructurado para el agente Evaluador."""
    status:        SolverStatus
    message:       str
    solver_code:   Optional[int]   = None   # código raw del solver
    solve_time:    Optional[float] = None   # segundos
    obj_value:     Optional[float] = None   # valor objetivo óptimo
    mip_gap:       Optional[float] = None   # gap MIP (si aplica)
    n_vars:        Optional[int]   = None   # número de variables
    n_constrs:     Optional[int]   = None   # número de restricciones
    traceback:     Optional[str]   = None   # traceback si hay error
    warnings:      list            = field(default_factory=list)
    suggestions:   list            = field(default_factory=list)

    def is_actionable(self) -> bool:
        """¿Tiene solución que se puede usar?"""
        return self.status in (SolverStatus.OPTIMAL, SolverStatus.TIME_LIMIT_SOL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status":      self.status.value,
            "message":     self.message,
            "solver_code": self.solver_code,
            "solve_time":  self.solve_time,
            "obj_value":   self.obj_value,
            "mip_gap":     self.mip_gap,
            "n_vars":      self.n_vars,
            "n_constrs":   self.n_constrs,
            "traceback":   self.traceback,
            "warnings":    self.warnings,
            "suggestions": self.suggestions,
            "actionable":  self.is_actionable(),
        }


class Diagnostics:
    """
    Clasifica y enriquece resultados del solver para el agente Evaluador.
    Soporta Gurobi, scipy y errores de código.
    """

    @staticmethod
    def from_gurobi_model(model, solve_time: float) -> DiagnosticReport:
        """Genera DiagnosticReport desde un Model de gurobipy ya resuelto."""
        import gurobipy as gp
        status_code = model.Status
        status = GUROBI_STATUS_MAP.get(status_code, SolverStatus.UNKNOWN)

        obj_value = None
        mip_gap   = None
        if status in (SolverStatus.OPTIMAL, SolverStatus.TIME_LIMIT_SOL):
            try:
                obj_value = model.ObjVal
            except gp.GurobiError:
                pass
            try:
                mip_gap = model.MIPGap
            except gp.GurobiError:
                pass

        report = DiagnosticReport(
            status      = status,
            message     = DIAGNOSTICS_MSG.get(status, ""),
            solver_code = status_code,
            solve_time  = solve_time,
            obj_value   = obj_value,
            mip_gap     = mip_gap,
            n_vars      = model.NumVars,
            n_constrs   = model.NumConstrs,
        )
        Diagnostics._add_suggestions(report, model=model)
        return report

    @staticmethod
    def from_scipy_result(result, solve_time: float,
                          n_vars: int, n_constrs: int) -> DiagnosticReport:
        """Genera DiagnosticReport desde scipy OptimizeResult."""
        status = SCIPY_STATUS_MAP.get(result.status, SolverStatus.UNKNOWN)
        # result.fun es el valor minimizado (-retorno_esperado); negamos para obtener retorno real
        obj_value = -float(result.fun) if status == SolverStatus.OPTIMAL else None

        report = DiagnosticReport(
            status      = status,
            message     = DIAGNOSTICS_MSG.get(status, result.message),
            solver_code = result.status,
            solve_time  = solve_time,
            obj_value   = obj_value,
            n_vars      = n_vars,
            n_constrs   = n_constrs,
        )
        Diagnostics._add_suggestions(report)
        return report

    @staticmethod
    def from_exception(exc: Exception, solve_time: float,
                       traceback_str: str) -> DiagnosticReport:
        """Genera DiagnosticReport desde una excepción."""
        exc_str = str(exc).lower()

        # Detectar tipo de error
        if any(kw in exc_str for kw in ("license", "licencia", "expired", "gurobi_home")):
            status = SolverStatus.LICENSE_ERROR
        elif any(kw in exc_str for kw in ("syntaxerror", "nameerror", "attributeerror",
                                           "typeerror", "importerror")):
            status = SolverStatus.CODE_ERROR
        else:
            status = SolverStatus.RUNTIME_ERROR

        return DiagnosticReport(
            status     = status,
            message    = DIAGNOSTICS_MSG.get(status, str(exc)),
            solve_time = solve_time,
            traceback  = traceback_str,
        )

    @staticmethod
    def flag_trivial(report: DiagnosticReport, cash_weight: float,
                     threshold: float = 0.95) -> DiagnosticReport:
        """Marca la solución como trivial si cash_weight > threshold."""
        if report.status == SolverStatus.OPTIMAL and cash_weight >= threshold:
            report.status = SolverStatus.TRIVIAL
            report.message = DIAGNOSTICS_MSG[SolverStatus.TRIVIAL]
            report.warnings.append(
                f"Peso en caja chica = {cash_weight:.1%} (umbral trivialidad: {threshold:.0%})"
            )
        return report

    @staticmethod
    def _add_suggestions(report: DiagnosticReport, model=None) -> None:
        """Agrega sugerencias de acción al reporte."""
        if report.status == SolverStatus.INFEASIBLE:
            report.suggestions = [
                "Reducir tolerancia de pérdida α (ej: pasar de 5% a 10%)",
                "Verificar que Σwᵢ + w₀ = 1 sea la única restricción de igualdad",
                "Ejecutar m.computeIIS() para identificar restricciones conflictivas",
            ]
        elif report.status == SolverStatus.UNBOUNDED:
            report.suggestions = [
                "Agregar restricción wᵢ ≤ max_weight (ej: 0.5 para diversificación)",
                "Verificar que la restricción presupuesto Σwᵢ + w₀ = 1 esté incluida",
            ]
        elif report.status == SolverStatus.TIME_LIMIT:
            report.suggestions = [
                "Reducir universo a top-50 acciones por capitalización",
                "Aumentar TimeLimit a 30s para exploración inicial",
                "Usar método simplex (Method=1) para LP puro",
            ]
        elif report.status == SolverStatus.LICENSE_ERROR:
            report.suggestions = [
                "Renovar licencia académica gratuita en gurobi.com/academia",
                "Usar solver de respaldo (scipy) con flag use_fallback=True",
                "Instalar Gurobi 11 con: pip install gurobipy==11.0.0",
            ]
        elif report.solve_time is not None and report.solve_time > 8.0:
            report.warnings.append(
                f"Tiempo de solución = {report.solve_time:.2f}s (límite operacional: 10s)"
            )
