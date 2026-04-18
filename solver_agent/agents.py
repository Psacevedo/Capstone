"""
agents.py -- Agentes LLM del pipeline P4.

Implementa ProgramadorAgent, EvaluadorAgent y ManagerAgent
usando la API de Anthropic con claude-opus-4-6 / claude-haiku-4-5.

Principio clave (OptiMUS): cada agente recibe SOLO el contexto relevante.
"""

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import anthropic

from .prompts import (
    PROGRAMADOR_SYSTEM, PROGRAMADOR_GENERATE, PROGRAMADOR_FIX,
    EVALUADOR_SYSTEM, EVALUADOR_EVALUATE,
    MANAGER_SYSTEM, MANAGER_DECIDE,
)

# ============================================================
# Configuracion de modelos
# ============================================================

# Manager y Evaluador: razonamiento complejo, pocas llamadas
MODEL_RAZONADOR = "claude-opus-4-6"

# Programador: generacion de codigo, muchas iteraciones → menor costo
MODEL_CODEGEN   = "claude-haiku-4-5"


# ============================================================
# Dataclasses de respuesta
# ============================================================

@dataclass
class EvaluadorDecision:
    decision:         str            # "accept" | "retry" | "abort"
    root_cause:       str
    feedback:         str
    priority_fix:     str
    confidence:       float
    raw_response:     str = ""

    def should_retry(self) -> bool:
        return self.decision == "retry"

    def should_accept(self) -> bool:
        return self.decision == "accept"

    def should_abort(self) -> bool:
        return self.decision == "abort"


@dataclass
class ManagerDecision:
    accion:              str           # "continuar" | "cambiar_estrategia" | "abortar"
    estrategia:          str
    contexto_adicional:  str
    razon:               str
    raw_response:        str = ""


# ============================================================
# Base: cliente Anthropic compartido
# ============================================================

def _make_client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY no encontrada. "
            "Configura: export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=key)


def _extract_text(response) -> str:
    """Extrae texto de una respuesta de la API de Anthropic."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _stream_and_collect(client: anthropic.Anthropic, **kwargs) -> tuple[str, Any]:
    """
    Hace una llamada a la API con streaming y retorna (texto, mensaje_final).
    Usa streaming por defecto para evitar timeouts en respuestas largas.
    """
    with client.messages.stream(**kwargs) as stream:
        text_parts = []
        for chunk in stream.text_stream:
            text_parts.append(chunk)
        final = stream.get_final_message()
    return "".join(text_parts), final


# ============================================================
# Agente Programador
# ============================================================

class ProgramadorAgent:
    """
    Genera y repara codigo Python/Gurobi para el LP de portafolios P4.

    Modelo: claude-haiku-4-5 (rapido, iteraciones frecuentes, menor costo).
    Contexto: solo los parametros del problema y el feedback del Evaluador.
    """

    def __init__(self, client: anthropic.Anthropic, verbose: bool = False):
        self.client  = client
        self.verbose = verbose
        self._log("Programador inicializado")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [Programador] {msg}", flush=True)

    def generate(self, problem_params: Dict, estrategia: str) -> str:
        """
        Genera codigo inicial para el problema dado.

        problem_params: dict con tickers, returns_scen, probs, alpha, etc.
        estrategia: nombre de la estrategia (ej: "Gurobi LP base")
        """
        self._log(f"Generando codigo ({estrategia})...")

        params_str = self._format_params(problem_params)

        prompt = PROGRAMADOR_GENERATE.format(
            problem_params=params_str,
            estrategia=estrategia,
        )

        text, _ = _stream_and_collect(
            self.client,
            model=MODEL_CODEGEN,
            max_tokens=4096,
            system=PROGRAMADOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        code = self._extract_code(text)
        self._log(f"Codigo generado ({len(code.splitlines())} lineas)")
        return code

    def fix(self, prev_code: str, decision: "EvaluadorDecision",
            solver_result, iteration: int) -> str:
        """
        Repara el codigo basandose en el feedback estructurado del Evaluador.

        Principio OptiMUS: el Programador recibe SOLO el feedback relevante,
        no el historial completo de iteraciones.
        """
        self._log(f"Reparando codigo (iter {iteration}) | causa: {decision.root_cause}")

        diag = solver_result.diagnostic
        weights_brief = ""
        if solver_result.weights:
            top3 = sorted(solver_result.weights.items(), key=lambda x: -x[1])[:3]
            weights_brief = str([(t, round(w, 4)) for t, w in top3])

        prompt = PROGRAMADOR_FIX.format(
            root_cause   = decision.root_cause,
            priority_fix = decision.priority_fix,
            feedback     = decision.feedback,
            prev_code    = prev_code,
            status       = diag.status.value,
            traceback    = (diag.traceback or "")[-1500:],  # ultimas 1500 chars
        )

        text, _ = _stream_and_collect(
            self.client,
            model=MODEL_CODEGEN,
            max_tokens=4096,
            system=PROGRAMADOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        code = self._extract_code(text)
        self._log(f"Codigo reparado ({len(code.splitlines())} lineas)")
        return code

    def _format_params(self, params: Dict) -> str:
        """Serializa los parametros del problema de forma legible para el LLM."""
        lines = [
            f"tickers      = {params.get('tickers', [])}",
            f"returns_scen = {params.get('returns_scen', {})}",
            f"probs        = {params.get('probs', {})}",
            f"alpha        = {params.get('alpha', 0.15)}",
            f"commission_k = {params.get('commission_k', 0.001)}",
            f"max_weight   = {params.get('max_weight', 1.0)}",
            f"time_limit   = {params.get('time_limit', 9.0)}",
        ]
        if params.get('prev_weights'):
            lines.append(f"prev_weights = {params['prev_weights']}")
        return "\n".join(lines)

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extrae el bloque de codigo Python de la respuesta del LLM."""
        # Buscar bloque ```python ... ```
        if "```python" in text:
            start = text.index("```python") + len("```python")
            end   = text.index("```", start)
            return text[start:end].strip()
        # Buscar bloque ``` ... ```
        if "```" in text:
            start = text.index("```") + 3
            end   = text.index("```", start)
            return text[start:end].strip()
        # Asumir que toda la respuesta es codigo
        return text.strip()


# ============================================================
# Agente Evaluador
# ============================================================

class EvaluadorAgent:
    """
    Interpreta DiagnosticReport y decide accept | retry | abort.

    Modelo: claude-opus-4-6 con adaptive thinking (razonamiento sobre fallos complejos).
    Contexto: solo el DiagnosticReport y el resultado de validacion.
    """

    def __init__(self, client: anthropic.Anthropic, verbose: bool = False):
        self.client  = client
        self.verbose = verbose
        self._log("Evaluador inicializado")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [Evaluador]   {msg}", flush=True)

    def evaluate(self, solver_result, iteration: int, max_iter: int) -> EvaluadorDecision:
        """
        Evalua un SolverResult y retorna una decision estructurada.
        Usa adaptive thinking para analizar causas raiz de fallos complejos.
        """
        self._log(f"Evaluando resultado (iter {iteration}) | status: {solver_result.status.value}")

        diag = solver_result.diagnostic
        val  = solver_result.validation or {}

        # Resumen compacto de pesos (evitar prompt gigante)
        weights_summary = ""
        if solver_result.weights:
            active = [(t, round(w, 4)) for t, w in solver_result.weights.items() if w > 1e-4]
            active.sort(key=lambda x: -x[1])
            weights_summary = str(active[:5]) + (" ..." if len(active) > 5 else "")

        prompt = EVALUADOR_EVALUATE.format(
            status       = diag.status.value,
            solver_used  = solver_result.solver_used,
            solve_time   = round(diag.solve_time or 0, 4),
            obj_value    = round(diag.obj_value or 0, 6) if diag.obj_value else "N/A",
            n_vars       = diag.n_vars or "N/A",
            n_constrs    = diag.n_constrs or "N/A",
            traceback    = (diag.traceback or "")[-800:],
            valid        = val.get("valid", "N/A"),
            violations   = val.get("violations", []),
            warnings     = diag.warnings[:3],   # max 3 warnings
            weights_summary = weights_summary,
            cash         = round(solver_result.cash or 0, 4) if solver_result.cash is not None else "N/A",
            iteration    = iteration,
            max_iter     = max_iter,
        )

        text, _ = _stream_and_collect(
            self.client,
            model   = MODEL_RAZONADOR,
            max_tokens = 1024,
            thinking = {"type": "adaptive"},
            system  = EVALUADOR_SYSTEM,
            messages = [{"role": "user", "content": prompt}],
        )

        decision = self._parse_decision(text)
        self._log(f"Decision: {decision.decision} | causa: {decision.root_cause}")
        return decision

    def _parse_decision(self, text: str) -> EvaluadorDecision:
        """Parsea el JSON de decision del Evaluador."""
        # Extraer JSON del texto
        raw = text.strip()
        if "```json" in raw:
            start = raw.index("```json") + 7
            end   = raw.index("```", start)
            raw   = raw[start:end].strip()
        elif "```" in raw:
            start = raw.index("```") + 3
            end   = raw.index("```", start)
            raw   = raw[start:end].strip()

        try:
            data = json.loads(raw)
            return EvaluadorDecision(
                decision     = data.get("decision", "abort"),
                root_cause   = data.get("root_cause", "desconocido"),
                feedback     = data.get("feedback", ""),
                priority_fix = data.get("priority_fix", ""),
                confidence   = float(data.get("confidence", 0.5)),
                raw_response = text,
            )
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: si el LLM no devolvio JSON valido
            return EvaluadorDecision(
                decision     = "retry",
                root_cause   = "parse_error",
                feedback     = f"No se pudo parsear la decision del Evaluador: {e}. Texto: {text[:200]}",
                priority_fix = "Verificar el formato del codigo generado",
                confidence   = 0.3,
                raw_response = text,
            )


# ============================================================
# Agente Manager
# ============================================================

class ManagerAgent:
    """
    Orquesta el loop entre Programador y Evaluador.

    Modelo: claude-opus-4-6 con adaptive thinking.
    Mantiene vision global del historial de intentos para evitar ciclos.

    Estrategias (escalada progresiva):
      1. Gurobi LP base (capas 0-1)
      2. Gurobi 2-SLP con escenarios (capas 0-2)
      3. scipy/HiGHS fallback (LP base)
      4. scipy universo reducido (top-20)
    """

    ESTRATEGIAS = [
        "Gurobi LP base (capas 0-1)",
        "Gurobi 2-SLP con escenarios (capas 0-2)",
        "scipy/HiGHS fallback (LP base)",
        "scipy universo reducido (top-20 por capitalizacion)",
    ]

    def __init__(self, client: anthropic.Anthropic, verbose: bool = False):
        self.client     = client
        self.verbose    = verbose
        self.historial: List[Dict] = []
        self._log("Manager inicializado")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [Manager]     {msg}", flush=True)

    def estrategia_inicial(self) -> str:
        return self.ESTRATEGIAS[0]

    def decide(self, iteration: int, max_iter: int,
                estrategia_actual: str,
                evaluador_decision: "EvaluadorDecision",
                solver_result) -> ManagerDecision:
        """
        Decide la siguiente accion del pipeline basandose en el historial global.
        """
        # Registrar intento en historial
        self.historial.append({
            "iter":      iteration,
            "estrategia": estrategia_actual,
            "status":    solver_result.status.value,
            "decision":  evaluador_decision.decision,
            "causa":     evaluador_decision.root_cause,
        })

        # Reglas rapidas sin llamar al LLM (ahorra costo)
        # Si el Evaluador acepto: continuar con esa decision
        if evaluador_decision.should_accept():
            return ManagerDecision(
                accion="continuar", estrategia=estrategia_actual,
                contexto_adicional="", razon="Evaluador acepto la solucion"
            )

        # Si se alcanzaron las iteraciones maximas: abortar
        if iteration >= max_iter:
            return ManagerDecision(
                accion="abortar", estrategia=estrategia_actual,
                contexto_adicional="",
                razon=f"Iteraciones maximas alcanzadas ({max_iter})"
            )

        # Si el Evaluador quiere abortar: respetar
        if evaluador_decision.should_abort():
            return ManagerDecision(
                accion="abortar", estrategia=estrategia_actual,
                contexto_adicional="",
                razon=f"Evaluador solicito abortar: {evaluador_decision.root_cause}"
            )

        # Contar intentos con la estrategia actual
        intentos_actuales = sum(
            1 for h in self.historial
            if h["estrategia"] == estrategia_actual
        )

        # Despues de 2 intentos fallidos con la misma estrategia: escalar
        if intentos_actuales >= 2:
            idx_actual = self.ESTRATEGIAS.index(estrategia_actual) if estrategia_actual in self.ESTRATEGIAS else -1
            siguiente_idx = idx_actual + 1

            if siguiente_idx >= len(self.ESTRATEGIAS):
                return ManagerDecision(
                    accion="abortar", estrategia=estrategia_actual,
                    contexto_adicional="",
                    razon="Todas las estrategias fallaron"
                )

            nueva_estrategia = self.ESTRATEGIAS[siguiente_idx]
            self._log(f"Escalando estrategia: {estrategia_actual} -> {nueva_estrategia}")

            # Para las ultimas 2 iteraciones: consultar al LLM Manager
            if iteration >= max_iter - 2:
                return self._llm_decide(iteration, max_iter, estrategia_actual,
                                        evaluador_decision, nueva_estrategia)

            return ManagerDecision(
                accion="cambiar_estrategia",
                estrategia=nueva_estrategia,
                contexto_adicional=f"La estrategia anterior ({estrategia_actual}) fallo {intentos_actuales} veces. Usa {nueva_estrategia}.",
                razon=f"Escalando a {nueva_estrategia} tras {intentos_actuales} fallos"
            )

        # Dentro del limite de intentos: continuar con retry
        return ManagerDecision(
            accion="continuar", estrategia=estrategia_actual,
            contexto_adicional="",
            razon=f"Intento {intentos_actuales}/2 con {estrategia_actual}"
        )

    def _llm_decide(self, iteration: int, max_iter: int,
                    estrategia_actual: str,
                    evaluador_decision: "EvaluadorDecision",
                    nueva_estrategia: str) -> ManagerDecision:
        """
        Consulta al LLM Manager para casos complejos (ultimas iteraciones).
        Usa adaptive thinking para razonamiento de mayor profundidad.
        """
        self._log("Consultando LLM para decision compleja...")

        historial_str = json.dumps(self.historial[-5:], indent=2, ensure_ascii=False)

        prompt = MANAGER_DECIDE.format(
            iteration       = iteration,
            max_iter        = max_iter,
            estrategia      = estrategia_actual,
            historial       = historial_str,
            ultimo_resultado = json.dumps({
                "decision":  evaluador_decision.decision,
                "causa":     evaluador_decision.root_cause,
                "feedback":  evaluador_decision.feedback[:200],
            }, ensure_ascii=False),
        )

        try:
            text, _ = _stream_and_collect(
                self.client,
                model    = MODEL_RAZONADOR,
                max_tokens = 512,
                thinking = {"type": "adaptive"},
                system   = MANAGER_SYSTEM,
                messages = [{"role": "user", "content": prompt}],
            )

            raw = text.strip()
            if "```" in raw:
                start = raw.index("```") + 3
                if "json" in raw[start:start+4]:
                    start += 4
                end = raw.index("```", start)
                raw = raw[start:end].strip()

            data = json.loads(raw)
            return ManagerDecision(
                accion             = data.get("accion", "continuar"),
                estrategia         = data.get("estrategia", nueva_estrategia),
                contexto_adicional = data.get("contexto_adicional", ""),
                razon              = data.get("razon", ""),
                raw_response       = text,
            )
        except Exception as e:
            self._log(f"Error en LLM Manager, usando fallback: {e}")
            return ManagerDecision(
                accion="cambiar_estrategia",
                estrategia=nueva_estrategia,
                contexto_adicional="",
                razon=f"Fallback: escalando a {nueva_estrategia}"
            )
