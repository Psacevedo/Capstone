"""
pipeline.py -- Orquestador principal del pipeline P4 supervisado por LLM.

Arquitectura (OptiMUS + OR-LLM-Agent):

  Input params
       |
       v
  Manager.estrategia_inicial()
       |
       v
  [Loop hasta max_iter o solucion aceptada]
       |
       +---> Programador.generate() / Programador.fix()
       |            |
       |            v
       |     SolverSandbox.run_code()
       |            |
       |            v
       |     Evaluador.evaluate()  -->  decision
       |            |
       |     Manager.decide()  -->  accion
       |            |
       +<--- retry / cambiar_estrategia
       |
       v
  PipelineResult (SolverResult + trazabilidad)
"""

import os
import sys
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from solver import SolverSandbox, SolverResult, SolverStatus
from solver.validators import RISK_PROFILES
from solver.models.portfolio_lp import generate_gurobi_code as gen_base_code
from solver.models.stochastic_lp import generate_gurobi_code as gen_2slp_code

from .agents import (
    ProgramadorAgent, EvaluadorAgent, ManagerAgent,
    EvaluadorDecision, ManagerDecision,
    _make_client,
)


# ============================================================
# Resultado del pipeline
# ============================================================

@dataclass
class IterationRecord:
    """Registro de una iteracion del loop."""
    iteration:   int
    estrategia:  str
    code:        str
    result:      SolverResult
    evaluacion:  EvaluadorDecision
    decision_manager: ManagerDecision
    duration_s:  float


@dataclass
class PipelineResult:
    """Resultado completo del pipeline con trazabilidad."""
    success:        bool
    final_result:   Optional[SolverResult]
    iterations:     List[IterationRecord] = field(default_factory=list)
    total_time_s:   float = 0.0
    total_llm_calls: int  = 0
    abort_reason:   str   = ""

    def to_dict(self) -> Dict:
        return {
            "success":         self.success,
            "total_time_s":    round(self.total_time_s, 3),
            "total_llm_calls": self.total_llm_calls,
            "n_iterations":    len(self.iterations),
            "abort_reason":    self.abort_reason,
            "final_status":    self.final_result.status.value if self.final_result else "none",
            "final_obj_value": self.final_result.obj_value if self.final_result else None,
            "final_weights":   self.final_result.weights if self.final_result else None,
            "final_cash":      self.final_result.cash if self.final_result else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def print_summary(self):
        """Imprime un resumen del pipeline."""
        print("\n" + "=" * 60)
        print("  Pipeline P4 -- Resumen de ejecucion")
        print("=" * 60)
        print(f"  Exito:        {'SI' if self.success else 'NO'}")
        print(f"  Iteraciones:  {len(self.iterations)}")
        print(f"  Llamadas LLM: {self.total_llm_calls}")
        print(f"  Tiempo total: {self.total_time_s:.2f}s")

        if self.abort_reason:
            print(f"  Razon abort:  {self.abort_reason}")

        if self.final_result and self.final_result.ok():
            r = self.final_result
            print(f"\n  Portafolio optimo:")
            print(f"    Retorno esperado: {r.obj_value:.4f} ({r.obj_value:.2%})")
            print(f"    Solver: {r.solver_used}")
            if r.weights:
                active = [(t, w) for t, w in r.weights.items() if w > 1e-4]
                active.sort(key=lambda x: -x[1])
                for t, w in active[:5]:
                    print(f"    {t:<8} {w:>7.2%}")
                if r.cash and r.cash > 1e-4:
                    print(f"    {'CASH':<8} {r.cash:>7.2%}")

        print("\n  Historial de iteraciones:")
        for rec in self.iterations:
            ev  = rec.evaluacion
            mgr = rec.decision_manager
            print(
                f"    Iter {rec.iteration}: [{rec.estrategia[:30]:<30}]"
                f"  status={rec.result.status.value:<18}"
                f"  eval={ev.decision:<7}"
                f"  mgr={mgr.accion}"
                f"  ({rec.duration_s:.2f}s)"
            )
        print()


# ============================================================
# Pipeline principal
# ============================================================

class P4Pipeline:
    """
    Pipeline LLM supervisado para optimizacion de portafolios P4.

    Parametros
    ----------
    api_key     : str  -- ANTHROPIC_API_KEY (o variable de entorno)
    max_iter    : int  -- iteraciones maximas del loop (default 5)
    verbose     : bool -- mostrar logs de cada agente
    time_limit  : float -- limite de tiempo del solver en segundos

    Uso:
        pipeline = P4Pipeline(api_key="sk-ant-...", verbose=True)
        result   = pipeline.run(
            tickers      = ["AAPL", "MSFT", "JNJ", ...],
            returns_scen = {"desf": {...}, "neutro": {...}, "fav": {...}},
            probs        = {"desf": 0.25, "neutro": 0.50, "fav": 0.25},
            profile      = "neutro",
        )
        result.print_summary()
    """

    def __init__(
        self,
        api_key:    Optional[str] = None,
        max_iter:   int   = 5,
        verbose:    bool  = False,
        time_limit: float = 9.0,
    ):
        self.max_iter   = max_iter
        self.verbose    = verbose
        self.time_limit = time_limit

        # Cliente Anthropic compartido entre todos los agentes.
        # Se inicializa de forma perezosa: run_direct() no requiere API key.
        self._api_key = api_key
        self._client  = None

        # Instanciar agentes (sin cliente por ahora)
        self.programador = ProgramadorAgent(None, verbose=verbose)
        self.evaluador   = EvaluadorAgent(None, verbose=verbose)
        self.manager     = ManagerAgent(None, verbose=verbose)

        # Sandbox de ejecucion (sin LLM, ejecucion determinista)
        self.sandbox = SolverSandbox(
            time_limit   = time_limit,
            use_fallback = True,
            verbose      = False,
        )

        self._llm_calls = 0

    def _ensure_client(self):
        """Inicializa el cliente Anthropic la primera vez que se necesita."""
        if self._client is None:
            self._client = _make_client(self._api_key)
            self.programador.client = self._client
            self.evaluador.client   = self._client
            self.manager.client     = self._client

    def _log(self, msg: str):
        if self.verbose:
            print(f"\n[Pipeline] {msg}", flush=True)

    # ------------------------------------------------------------------ #
    # API publica                                                          #
    # ------------------------------------------------------------------ #

    def run(
        self,
        tickers:       List[str],
        returns_scen:  Dict[str, Dict[str, float]],
        probs:         Dict[str, float],
        profile:       str = "neutro",
        commission_k:  float = 0.001,
        max_weight:    float = 1.0,
        prev_weights:  Optional[Dict[str, float]] = None,
    ) -> PipelineResult:
        """
        Ejecuta el pipeline completo.

        Retorna PipelineResult con el portafolio optimo y trazabilidad completa.
        """
        self._ensure_client()
        t0 = time.perf_counter()
        self._log(f"Iniciando pipeline | perfil={profile} | tickers={len(tickers)}")

        alpha = RISK_PROFILES.get(profile, 0.15)
        returns_mean = {
            t: sum(probs.get(s, 1/3) * returns_scen[s].get(t, 0.0) for s in returns_scen)
            for t in tickers
        }

        # Parametros del problema para los agentes
        problem_params = {
            "tickers":      tickers,
            "returns_scen": returns_scen,
            "returns_mean": returns_mean,
            "probs":        probs,
            "alpha":        alpha,
            "commission_k": commission_k,
            "max_weight":   max_weight,
            "time_limit":   self.time_limit,
            "prev_weights": prev_weights,
            "profile":      profile,
        }

        iterations: List[IterationRecord] = []
        estrategia   = self.manager.estrategia_inicial()
        current_code = None
        last_result  = None
        last_eval    = None

        for iteration in range(1, self.max_iter + 1):
            iter_t0 = time.perf_counter()
            self._log(f"--- Iteracion {iteration}/{self.max_iter} | {estrategia} ---")

            # 1. Programador: generar o reparar codigo
            if current_code is None:
                current_code = self.programador.generate(problem_params, estrategia)
                self._llm_calls += 1
            else:
                current_code = self.programador.fix(
                    current_code, last_eval, last_result, iteration
                )
                self._llm_calls += 1

            # Aplicar ajustes de estrategia al codigo si es necesario
            current_code = self._apply_strategy_adjustments(
                current_code, estrategia, problem_params
            )

            # 2. Sandbox: ejecutar codigo
            self._log("Ejecutando sandbox...")
            last_result = self.sandbox.run_code(
                current_code,
                profile=profile,
                returns_scenario=returns_scen.get("desf", {}),
            )
            self._log(f"Sandbox resultado: {last_result.status.value}")

            # 3. Evaluador: interpretar resultado
            last_eval = self.evaluador.evaluate(last_result, iteration, self.max_iter)
            self._llm_calls += 1
            self._log(f"Evaluador: {last_eval.decision} | {last_eval.root_cause}")

            # 4. Manager: decidir siguiente accion
            mgr_decision = self.manager.decide(
                iteration, self.max_iter, estrategia, last_eval, last_result
            )
            # Manager llama al LLM solo en casos complejos (internamente)

            # Registrar iteracion
            iterations.append(IterationRecord(
                iteration        = iteration,
                estrategia       = estrategia,
                code             = current_code,
                result           = last_result,
                evaluacion       = last_eval,
                decision_manager = mgr_decision,
                duration_s       = time.perf_counter() - iter_t0,
            ))

            self._log(f"Manager: {mgr_decision.accion} | {mgr_decision.razon}")

            # 5. Actuar segun decision del Manager
            if mgr_decision.accion == "abortar":
                return PipelineResult(
                    success       = last_eval.should_accept(),
                    final_result  = last_result if last_eval.should_accept() else None,
                    iterations    = iterations,
                    total_time_s  = time.perf_counter() - t0,
                    total_llm_calls = self._llm_calls,
                    abort_reason  = mgr_decision.razon,
                )

            if mgr_decision.accion == "continuar" and last_eval.should_accept():
                return PipelineResult(
                    success         = True,
                    final_result    = last_result,
                    iterations      = iterations,
                    total_time_s    = time.perf_counter() - t0,
                    total_llm_calls = self._llm_calls,
                )

            if mgr_decision.accion == "cambiar_estrategia":
                estrategia   = mgr_decision.estrategia
                current_code = None   # forzar regeneracion con nueva estrategia
                # Actualizar problem_params con contexto adicional del Manager
                if mgr_decision.contexto_adicional:
                    problem_params["_manager_context"] = mgr_decision.contexto_adicional
                # Reducir universo si estrategia lo requiere
                if "reducido" in estrategia.lower():
                    problem_params = self._reduce_universe(problem_params)

        # Loop terminado sin solucion aceptada
        return PipelineResult(
            success         = last_eval.should_accept() if last_eval else False,
            final_result    = last_result if (last_eval and last_eval.should_accept()) else None,
            iterations      = iterations,
            total_time_s    = time.perf_counter() - t0,
            total_llm_calls = self._llm_calls,
            abort_reason    = f"Iteraciones maximas ({self.max_iter}) alcanzadas sin solucion",
        )

    # ------------------------------------------------------------------ #
    # Metodo directo: omite LLM y resuelve con modelo pre-armado          #
    # Util para benchmarking y pruebas de regresion                       #
    # ------------------------------------------------------------------ #

    def run_direct(
        self,
        tickers:      List[str],
        returns_scen: Dict[str, Dict[str, float]],
        probs:        Dict[str, float],
        profile:      str = "neutro",
        commission_k: float = 0.001,
        max_weight:   float = 1.0,
        prev_weights: Optional[Dict[str, float]] = None,
    ) -> SolverResult:
        """
        Resuelve directamente con el sandbox (sin LLM).
        Modo de referencia para comparar con el pipeline supervisado.
        """
        alpha = RISK_PROFILES.get(profile, 0.15)
        returns_mean = {
            t: sum(probs.get(s, 1/3) * returns_scen[s].get(t, 0.0) for s in returns_scen)
            for t in tickers
        }
        return self.sandbox.run_model(
            tickers=tickers, returns_mean=returns_mean,
            returns_scen=returns_scen, probs=probs,
            profile=profile, max_weight=max_weight,
            commission_k=commission_k, prev_weights=prev_weights,
        )

    # ------------------------------------------------------------------ #
    # Helpers privados                                                     #
    # ------------------------------------------------------------------ #

    def _apply_strategy_adjustments(
        self, code: str, estrategia: str, params: Dict
    ) -> str:
        """
        Aplica ajustes deterministicos al codigo segun la estrategia.
        No usa LLM — modificaciones puntuales y predecibles.
        """
        # Si el LLM genero codigo vacio o muy corto, usar codegen pre-armado
        if len(code.strip()) < 50:
            self._log("Codigo vacio/muy corto, usando codegen pre-armado")
            return self._fallback_codegen(estrategia, params)

        # Para estrategias scipy: asegurar que no usen gurobipy
        if "scipy" in estrategia.lower() and "gurobipy" in code:
            self._log("Estrategia scipy pero codigo usa gurobipy, regenerando")
            return self._fallback_codegen(estrategia, params)

        return code

    def _fallback_codegen(self, estrategia: str, params: Dict) -> str:
        """Usa los generadores pre-armados como fallback deterministico."""
        tickers = params["tickers"]
        alpha   = params["alpha"]
        returns_scen = params["returns_scen"]
        probs   = params["probs"]

        if "scipy" in estrategia.lower():
            # Generar codigo scipy directamente
            return self._scipy_code(tickers, returns_scen, probs, alpha, params)
        elif "2-SLP" in estrategia or "escenarios" in estrategia:
            return gen_2slp_code(
                tickers=tickers, returns_scen=returns_scen, probs=probs,
                alpha=alpha, commission_k=params.get("commission_k", 0.001),
                prev_weights=params.get("prev_weights"),
                max_weight=params.get("max_weight", 1.0),
                time_limit=params.get("time_limit", 9.0),
            )
        else:
            returns_desf = returns_scen.get("desf", {t: 0.0 for t in tickers})
            return gen_base_code(
                tickers=tickers,
                returns_mean=params["returns_mean"],
                returns_desf=returns_desf,
                alpha=alpha,
                commission_k=params.get("commission_k", 0.001),
                prev_weights=params.get("prev_weights"),
                max_weight=params.get("max_weight", 1.0),
                time_limit=params.get("time_limit", 9.0),
            )

    def _scipy_code(self, tickers, returns_scen, probs, alpha, params) -> str:
        """Genera codigo scipy para el fallback."""
        returns_mean = params.get("returns_mean", {
            t: sum(probs.get(s, 1/3) * returns_scen[s].get(t, 0.0) for s in returns_scen)
            for t in tickers
        })
        max_weight = params.get("max_weight", 1.0)
        time_limit = params.get("time_limit", 9.0)
        commission_k = params.get("commission_k", 0.001)

        lines = [
            "import numpy as np",
            "from scipy.optimize import linprog",
            "import time as _time",
            "",
            f"tickers = {repr(tickers)}",
            f"returns_mean = {repr(returns_mean)}",
            f"returns_desf = {repr(returns_scen.get('desf', {}))}",
            f"alpha = {alpha}",
            f"max_weight = {max_weight}",
            "",
            "n = len(tickers)",
            "# Objetivo: minimizar -retorno_esperado",
            "c = np.array([-returns_mean.get(t, 0.0) for t in tickers] + [0.0])",
            "",
            "# R1: presupuesto sum(w)+w0=1",
            "A_eq = np.ones((1, n+1))",
            "b_eq = np.array([1.0])",
            "",
            "# R3: tolerancia perdida",
            "r_desf = np.array([returns_desf.get(t, 0.0) for t in tickers])",
            "A_ub = np.concatenate([-r_desf, [0.0]]).reshape(1, -1)",
            "b_ub = np.array([alpha])",
            "",
            f"bounds = [(0.0, {max_weight})] * n + [(0.0, 1.0)]",
            "",
            "_t0 = _time.perf_counter()",
            "res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,",
            "              bounds=bounds, method='highs',",
            f"              options={{'time_limit': {time_limit}}})",
            "",
            "# Exponer resultado para el sandbox",
            "_model   = None",
            "_weights = {t: float(res.x[i]) for i, t in enumerate(tickers)} if res.status == 0 else {}",
            "_cash    = float(res.x[-1]) if res.status == 0 else 0.0",
            "",
            "# Emular interfaz gp.Model para el wrapper del sandbox",
            "class _FakeModel:",
            "    Status = 2 if res.status == 0 else (3 if res.status == 2 else 9)",
            "    NumVars = n + 1",
            "    NumConstrs = 2",
            "    ObjVal = -float(res.fun) if res.status == 0 else None",
            "    def optimize(self): pass",
            "_model = _FakeModel()",
        ]

        # Adaptar variables _weights y _cash para que el wrapper las detecte
        # El wrapper espera _weights dict de Vars con .X, pero podemos usar
        # un objeto simple
        lines += [
            "",
            "class _W:",
            "    def __init__(self, v): self.X = v",
            "_weights = {t: _W(float(res.x[i])) for i, t in enumerate(tickers)} if res.status == 0 else {}",
            "_cash_obj = _W(float(res.x[-1])) if res.status == 0 else _W(0.0)",
            "_cash = _cash_obj",
        ]

        return "\n".join(lines)

    def _reduce_universe(self, params: Dict) -> Dict:
        """
        Reduce el universo de acciones a top-20 por retorno esperado.
        Se usa cuando la estrategia 'scipy universo reducido' se activa.
        """
        tickers = params["tickers"]
        returns_mean = params.get("returns_mean", {t: 0.0 for t in tickers})

        if len(tickers) <= 20:
            return params  # Ya es pequeno

        # Tomar top-20 por retorno esperado
        top20 = sorted(tickers, key=lambda t: -returns_mean.get(t, 0.0))[:20]
        self._log(f"Universo reducido: {len(tickers)} -> {len(top20)} acciones")

        # Filtrar todos los dicts de retornos
        new_params = dict(params)
        new_params["tickers"]      = top20
        new_params["returns_mean"] = {t: returns_mean[t] for t in top20}
        new_params["returns_scen"] = {
            s: {t: params["returns_scen"][s].get(t, 0.0) for t in top20}
            for s in params["returns_scen"]
        }
        return new_params
