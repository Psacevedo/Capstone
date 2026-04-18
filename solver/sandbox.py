"""
sandbox.py — Ejecutor supervisado para código Gurobi generado por agentes LLM.

Dos modos de uso:
  1. run_code(code_str)    — ejecuta código Python arbitrario en subprocess con timeout
  2. run_model(params)     — ejecuta modelo P4 parametrizado (Gurobi o fallback scipy)

Flujo para el pipeline LLM:
  Programador (LLM) genera código
        ↓
  SolverSandbox.run_code(code_str)
        ↓
  DiagnosticReport → Evaluador (LLM)
        ↓
  Si no óptimo → feedback al Programador → iterar
"""

import os
import sys
import json
import time
import tempfile
import textwrap
import traceback
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .diagnostics import Diagnostics, DiagnosticReport, SolverStatus
from .validators import PortfolioValidator, RISK_PROFILES
from .fallback import ScipyPortfolioSolver, build_scenario_returns


# ============================================================
# Resultado unificado de ejecución
# ============================================================

@dataclass
class SolverResult:
    """Resultado completo devuelto al agente Evaluador."""
    status:      SolverStatus
    diagnostic:  DiagnosticReport
    weights:     Optional[Dict[str, float]]      = None  # {ticker: weight}
    cash:        Optional[float]                 = None  # w₀
    obj_value:   Optional[float]                 = None  # retorno esperado
    validation:  Optional[Dict]                  = None  # ValidationResult.to_dict()
    summary:     Optional[Dict]                  = None  # portfolio_summary()
    solver_used: str                             = "unknown"
    raw_output:  Optional[str]                   = None  # stdout del subprocess

    def ok(self) -> bool:
        return self.diagnostic.is_actionable()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status":      self.status.value,
            "ok":          self.ok(),
            "solver_used": self.solver_used,
            "diagnostic":  self.diagnostic.to_dict(),
            "weights":     self.weights,
            "cash":        self.cash,
            "obj_value":   self.obj_value,
            "validation":  self.validation,
            "summary":     self.summary,
            "raw_output":  self.raw_output,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ============================================================
# Sandbox principal
# ============================================================

class SolverSandbox:
    """
    Sandbox supervisado de ejecución para el optimizador de portafolios P4.

    Parámetros
    ----------
    time_limit      : float  — tiempo máximo de resolución en segundos (default 9s)
    use_fallback    : bool   — usar scipy si Gurobi no está disponible
    gurobi_home     : str    — ruta a instalación Gurobi (GUROBI_HOME)
    license_file    : str    — ruta al archivo gurobi.lic
    verbose         : bool   — imprimir logs del sandbox
    max_retries     : int    — reintentos automáticos ante CODE_ERROR
    """

    GUROBI_WRAPPER_TEMPLATE = textwrap.dedent("""
    import os, sys, json, traceback, time
    os.environ.setdefault('GUROBI_HOME',    r'{gurobi_home}')
    os.environ.setdefault('GRB_LICENSE_FILE', r'{license_file}')

    _result = {{'status': 'code_error', 'weights': None, 'cash': None,
                'obj_value': None, 'solver_code': None, 'solve_time': None,
                'n_vars': None, 'n_constrs': None, 'traceback': None}}
    _t0 = time.perf_counter()
    try:
        # ===== CÓDIGO LLM =====
    {user_code}
        # ===== FIN CÓDIGO LLM =====

        # Extraer resultado del modelo Gurobi
        # El código LLM debe exponer: _model (gp.Model), _weights (dict), _cash (float)
        import gurobipy as gp
        _result['solver_code'] = _model.Status
        _result['solve_time']  = time.perf_counter() - _t0
        _result['n_vars']      = _model.NumVars
        _result['n_constrs']   = _model.NumConstrs
        if _model.Status == 2:  # OPTIMAL
            _result['status']    = 'optimal'
            _result['obj_value'] = _model.ObjVal
            _result['weights']   = {{t: v.X for t, v in _weights.items()}}
            _result['cash']      = _cash.X
        elif _model.Status == 3:
            _result['status'] = 'infeasible'
        elif _model.Status == 5:
            _result['status'] = 'unbounded'
        elif _model.Status in (9, 10, 16):
            _result['status'] = 'time_limit'
            try:
                _result['obj_value'] = _model.ObjVal
                _result['weights']   = {{t: v.X for t, v in _weights.items()}}
                _result['cash']      = _cash.X
            except: pass
        else:
            _result['status'] = f'gurobi_status_{{_model.Status}}'
    except Exception as _e:
        _result['traceback'] = traceback.format_exc()
        _result['solve_time'] = time.perf_counter() - _t0
        err = str(_e).lower()
        if any(k in err for k in ('license', 'expired', 'gurobi_home')):
            _result['status'] = 'license_error'
        elif any(k in err for k in ('syntaxerror','nameerror','attributeerror')):
            _result['status'] = 'code_error'
        else:
            _result['status'] = 'runtime_error'

    print('__SANDBOX_RESULT__' + json.dumps(_result))
    """)

    def __init__(
        self,
        time_limit:   float = 9.0,
        use_fallback: bool  = True,
        gurobi_home:  str   = "",
        license_file: str   = "",
        verbose:      bool  = False,
        max_retries:  int   = 0,
    ):
        self.time_limit   = time_limit
        self.use_fallback = use_fallback
        self.verbose      = verbose
        self.max_retries  = max_retries

        # Resolver rutas Gurobi
        self.gurobi_home  = gurobi_home  or os.environ.get("GUROBI_HOME", "")
        self.license_file = license_file or os.environ.get(
            "GRB_LICENSE_FILE",
            os.path.expanduser("~/gurobi.lic")
        )

    # ------------------------------------------------------------------ #
    # Modo 1: Ejecutar código LLM en subprocess                           #
    # ------------------------------------------------------------------ #

    def run_code(self, code_str: str,
                 profile: str = "neutro",
                 returns_scenario: Optional[Dict[str, float]] = None
                 ) -> SolverResult:
        """
        Ejecuta código Python/Gurobi generado por el agente Programador.

        El código DEBE definir las variables:
          _model   : gp.Model  — modelo ya resuelto
          _weights : dict      — {ticker: gp.Var}
          _cash    : gp.Var    — variable de caja chica

        Parámetros
        ----------
        code_str : str   — código Python generado por el LLM
        profile  : str   — perfil de riesgo para validación
        returns_scenario : dict — retornos escenario desfavorable (para validar R3)
        """
        t0 = time.perf_counter()

        # Envolver código LLM en el wrapper de extracción de resultados
        indented_code = textwrap.indent(code_str, "    ")
        wrapper = self.GUROBI_WRAPPER_TEMPLATE.format(
            gurobi_home  = self.gurobi_home,
            license_file = self.license_file,
            user_code    = indented_code,
        )

        raw_output, tb_str = "", ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(wrapper)
                tmp_path = f.name

            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=self.time_limit + 2   # margen extra para overhead subprocess
            )
            raw_output = proc.stdout + proc.stderr

        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - t0
            report  = DiagnosticReport(
                status     = SolverStatus.TIME_LIMIT,
                message    = Diagnostics.from_exception(
                    Exception("TimeoutExpired"), elapsed, ""
                ).message,
                solve_time = elapsed,
            )
            return SolverResult(
                status=SolverStatus.TIME_LIMIT, diagnostic=report,
                solver_used="gurobi_subprocess", raw_output=raw_output
            )

        except Exception as e:
            elapsed  = time.perf_counter() - t0
            tb_str   = traceback.format_exc()
            report   = Diagnostics.from_exception(e, elapsed, tb_str)
            return SolverResult(
                status=report.status, diagnostic=report,
                solver_used="gurobi_subprocess", raw_output=raw_output
            )

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # Parsear resultado del subprocess
        return self._parse_subprocess_output(
            raw_output, time.perf_counter() - t0,
            profile=profile, returns_scenario=returns_scenario
        )

    def _parse_subprocess_output(
        self, raw_output: str, elapsed: float,
        profile: str = "neutro",
        returns_scenario: Optional[Dict[str, float]] = None
    ) -> SolverResult:
        """Extrae el JSON de resultado del stdout del subprocess."""
        marker = "__SANDBOX_RESULT__"
        result_json = None

        for line in raw_output.splitlines():
            if marker in line:
                try:
                    result_json = json.loads(line.split(marker, 1)[1])
                except json.JSONDecodeError:
                    pass
                break

        if result_json is None:
            report = DiagnosticReport(
                status     = SolverStatus.CODE_ERROR,
                message    = "El subprocess no produjo resultado JSON. Revisar traceback.",
                solve_time = elapsed,
                traceback  = raw_output[-3000:],  # últimos 3000 chars
            )
            return SolverResult(
                status=SolverStatus.CODE_ERROR, diagnostic=report,
                solver_used="gurobi_subprocess", raw_output=raw_output
            )

        # Construir DiagnosticReport desde el dict
        status_str  = result_json.get("status", "unknown")
        solve_time  = result_json.get("solve_time") or elapsed
        obj_value   = result_json.get("obj_value")
        weights_raw = result_json.get("weights")
        cash        = result_json.get("cash")
        tb_str      = result_json.get("traceback")

        # Mapear status string a enum
        status_map_str = {
            "optimal":       SolverStatus.OPTIMAL,
            "infeasible":    SolverStatus.INFEASIBLE,
            "unbounded":     SolverStatus.UNBOUNDED,
            "time_limit":    SolverStatus.TIME_LIMIT,
            "license_error": SolverStatus.LICENSE_ERROR,
            "code_error":    SolverStatus.CODE_ERROR,
            "runtime_error": SolverStatus.RUNTIME_ERROR,
        }
        status = status_map_str.get(status_str, SolverStatus.UNKNOWN)

        from .diagnostics import DIAGNOSTICS_MSG
        report = DiagnosticReport(
            status     = status,
            message    = DIAGNOSTICS_MSG.get(status, status_str),
            solver_code= result_json.get("solver_code"),
            solve_time = solve_time,
            obj_value  = obj_value,
            n_vars     = result_json.get("n_vars"),
            n_constrs  = result_json.get("n_constrs"),
            traceback  = tb_str,
        )

        # Si no hay solución, intentar fallback scipy
        if not report.is_actionable():
            if self.use_fallback and status == SolverStatus.LICENSE_ERROR:
                if self.verbose:
                    print("[sandbox] Gurobi no disponible → activando fallback scipy")
                report.warnings.append(
                    "Gurobi no disponible. Resultado producido por solver de respaldo (scipy/HiGHS)."
                )
            return SolverResult(
                status=status, diagnostic=report,
                solver_used="gurobi_subprocess", raw_output=raw_output
            )

        # Validar solución
        weights = {t: float(w) for t, w in weights_raw.items()} if weights_raw else {}
        cash_w  = float(cash) if cash is not None else 0.0

        # Marcar trivial
        report = Diagnostics.flag_trivial(report, cash_w)

        validation = None
        summary    = None
        if weights:
            validator = PortfolioValidator(
                weights=weights, cash=cash_w,
                returns_scenario=returns_scenario or {},
                profile=profile,
            )
            val_result = validator.validate()
            validation = val_result.to_dict()
            summary    = validator.portfolio_summary()
            for warn in val_result.warnings:
                report.warnings.append(warn)

        return SolverResult(
            status      = report.status,
            diagnostic  = report,
            weights     = weights,
            cash        = cash_w,
            obj_value   = obj_value,
            validation  = validation,
            summary     = summary,
            solver_used = "gurobi_subprocess",
            raw_output  = raw_output,
        )

    # ------------------------------------------------------------------ #
    # Modo 2: Ejecutar modelo parametrizado (Gurobi nativo o scipy)       #
    # ------------------------------------------------------------------ #

    def run_model(
        self,
        tickers:        List[str],
        returns_mean:   Dict[str, float],
        returns_scen:   Dict[str, Dict[str, float]],
        probs:          Dict[str, float],
        profile:        str   = "neutro",
        max_weight:     float = 1.0,
        commission_k:   float = 0.001,
        prev_weights:   Optional[Dict[str, float]] = None,
    ) -> SolverResult:
        """
        Resuelve el modelo P4 (capas 0-2) con parámetros explícitos.

        Intenta Gurobi primero; si falla, usa scipy como respaldo.

        Parámetros
        ----------
        tickers      : lista de tickers en el universo
        returns_mean : {ticker: retorno_esperado}
        returns_scen : {'desf':{t:r}, 'neutro':{t:r}, 'fav':{t:r}}
        probs        : {'desf': 0.25, 'neutro': 0.50, 'fav': 0.25}
        profile      : perfil de riesgo ('muy_conservador',...,'muy_arriesgado')
        max_weight   : concentración máxima por acción
        commission_k : tasa de comisión k
        prev_weights : pesos previos para calcular costo de rebalanceo
        """
        alpha = RISK_PROFILES.get(profile, 0.15)

        # -- Intentar Gurobi nativo ---
        gurobi_result = self._try_gurobi(
            tickers, returns_mean, returns_scen, probs,
            alpha, max_weight, commission_k, prev_weights
        )
        if gurobi_result is not None:
            return gurobi_result

        # -- Fallback scipy ---
        if not self.use_fallback:
            report = DiagnosticReport(
                status  = SolverStatus.LICENSE_ERROR,
                message = "Gurobi no disponible y use_fallback=False.",
            )
            return SolverResult(status=SolverStatus.LICENSE_ERROR, diagnostic=report)

        if self.verbose:
            print("[sandbox] Gurobi no disponible → scipy/HiGHS")

        return self._run_scipy(
            tickers, returns_mean, returns_scen, probs,
            alpha, max_weight, commission_k, prev_weights, profile
        )

    def _try_gurobi(
        self, tickers, returns_mean, returns_scen, probs,
        alpha, max_weight, commission_k, prev_weights
    ) -> Optional[SolverResult]:
        """Intenta resolver con gurobipy; retorna None si no disponible."""
        try:
            import gurobipy as gp
        except (ImportError, TypeError, FileNotFoundError, OSError):
            # gurobipy lanza TypeError/OSError si GUROBI_HOME no está seteado
            return None

        try:
            gurobi_home = self.gurobi_home
            if gurobi_home:
                os.environ["GUROBI_HOME"] = gurobi_home
            if self.license_file:
                os.environ["GRB_LICENSE_FILE"] = self.license_file

            t0 = time.perf_counter()
            m  = gp.Model("portfolio_p4")
            m.Params.TimeLimit    = self.time_limit
            m.Params.OutputFlag   = int(self.verbose)
            m.Params.LogToConsole = int(self.verbose)

            n = len(tickers)

            # Variables de peso
            w = {t: m.addVar(lb=0.0, ub=max_weight, name=f"w_{t}") for t in tickers}
            w0 = m.addVar(lb=0.0, ub=1.0, name="w_cash")

            # Variables para comisiones (Δ⁺, Δ⁻)
            if prev_weights and commission_k > 0:
                dp = {t: m.addVar(lb=0.0, name=f"dp_{t}") for t in tickers}
                dn = {t: m.addVar(lb=0.0, name=f"dn_{t}") for t in tickers}
                for t in tickers:
                    pw = prev_weights.get(t, 0.0)
                    m.addConstr(w[t] - pw == dp[t] - dn[t], name=f"delta_{t}")
                # Costo de comisión (aproximación: k·Σ(Δ⁺+Δ⁻), asume V=1)
                commission_cost = gp.quicksum(
                    commission_k * (dp[t] + dn[t]) for t in tickers
                )
            else:
                commission_cost = 0.0

            m.update()

            # Objetivo: max E[r]·w
            expected_ret = gp.quicksum(
                sum(probs.get(s, 1/3) * returns_scen[s].get(t, 0.0) for s in returns_scen)
                * w[t]
                for t in tickers
            )
            m.setObjective(expected_ret - commission_cost, gp.GRB.MAXIMIZE)

            # R1: Presupuesto
            m.addConstr(
                gp.quicksum(w[t] for t in tickers) + w0 == 1.0,
                name="budget"
            )

            # R3: Tolerancia de pérdida (escenario desfavorable)
            if "desf" in returns_scen:
                m.addConstr(
                    gp.quicksum(returns_scen["desf"].get(t, 0.0) * w[t] for t in tickers)
                    >= -alpha,
                    name="loss_tolerance"
                )

            m.optimize()
            solve_time = time.perf_counter() - t0

            report = Diagnostics.from_gurobi_model(m, solve_time)

            if not report.is_actionable():
                return SolverResult(
                    status=report.status, diagnostic=report,
                    solver_used="gurobi_native"
                )

            weights = {t: w[t].X for t in tickers}
            cash    = w0.X

            report = Diagnostics.flag_trivial(report, cash)

            validator  = PortfolioValidator(
                weights=weights, cash=cash,
                returns_scenario=returns_scen.get("desf", {}),
            )
            val_result = validator.validate()
            for warn in val_result.warnings:
                report.warnings.append(warn)

            return SolverResult(
                status     = report.status,
                diagnostic = report,
                weights    = weights,
                cash       = cash,
                obj_value  = float(report.obj_value) if report.obj_value else None,
                validation = val_result.to_dict(),
                summary    = validator.portfolio_summary(),
                solver_used= "gurobi_native",
            )

        except Exception as e:
            tb_str = traceback.format_exc()
            report = Diagnostics.from_exception(e, 0.0, tb_str)
            if self.verbose:
                print(f"[sandbox] Gurobi error: {e}")
            # Si es error de licencia/instalación, retornar None para activar fallback
            if report.status in (SolverStatus.LICENSE_ERROR, SolverStatus.RUNTIME_ERROR):
                return None
            return SolverResult(
                status=report.status, diagnostic=report,
                solver_used="gurobi_native"
            )

    def _run_scipy(
        self, tickers, returns_mean, returns_scen, probs,
        alpha, max_weight, commission_k, prev_weights, profile
    ) -> SolverResult:
        """Resuelve con ScipyPortfolioSolver (fallback)."""
        solver = ScipyPortfolioSolver(
            tickers=tickers,
            returns_mean=returns_mean,
            returns_scen=returns_scen,
            probs=probs,
            alpha=alpha,
            max_weight=max_weight,
            time_limit=self.time_limit,
            prev_weights=prev_weights,
            commission_k=commission_k,
        )
        x, report = solver.solve()

        if x is None:
            return SolverResult(
                status=report.status, diagnostic=report,
                solver_used="scipy_fallback"
            )

        weights = {t: float(x[i]) for i, t in enumerate(tickers)}
        cash    = float(x[-1])

        report = Diagnostics.flag_trivial(report, cash)

        validator  = PortfolioValidator(
            weights=weights, cash=cash,
            returns_scenario=returns_scen.get("desf", {}),
            profile=profile,
        )
        val_result = validator.validate()
        for warn in val_result.warnings:
            report.warnings.append(warn)

        return SolverResult(
            status     = report.status,
            diagnostic = report,
            weights    = weights,
            cash       = cash,
            obj_value  = report.obj_value,
            validation = val_result.to_dict(),
            summary    = validator.portfolio_summary(),
            solver_used= "scipy_fallback",
        )
