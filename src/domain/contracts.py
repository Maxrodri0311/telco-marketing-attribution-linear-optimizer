"""
src/domain/contracts.py - Protocolos de Inversion de Dependencias (DIP).
Contratos abstractos para ingesta, almacenamiento, optimizacion y explicabilidad.
Prohibido acoplar implementaciones de infraestructura concretas en el dominio.
"""

from typing import Protocol, List, Dict, Any, Optional
import pandas as pd
from src.domain.entities import (
    B2BLeadSurvivalProfile,
    BudgetOptimizationRequest,
    OptimizationAllocationResult,
    ChannelAttributionExplanation,
    MarketingChannel
)
from pydantic import BaseModel

class ExecutionContext(BaseModel):
    """Contexto de ejecucion analitica."""
    execution_id: str = "default_run"
    target_metric: float = 0.0
    is_active: bool = True


class MarketingDataIngestionProtocol(Protocol):
    """Contrato para adaptadores de ingesta columnar de telemetria de marketing."""
    def load_lead_profiles(self, file_path: str, limit: Optional[int] = None) -> List[B2BLeadSurvivalProfile]:
        """Carga y parsea perfiles de supervivencia B2B desde parquet particionado."""
        ...


class MarketingOptimizationEngineProtocol(Protocol):
    """Contrato para solvers de optimizacion matematica de presupuesto."""
    def solve_budget_allocation(
        self,
        request: BudgetOptimizationRequest,
        historical_leads: List[B2BLeadSurvivalProfile]
    ) -> OptimizationAllocationResult:
        """Resuelve el problema primal restringido y extrae variables duales."""
        ...


class AttributionExplainerProtocol(Protocol):
    """Contrato para motores de explicabilidad XAI y descomposicion marginal."""
    def explain_allocations(
        self,
        result: OptimizationAllocationResult,
        request: BudgetOptimizationRequest
    ) -> List[ChannelAttributionExplanation]:
        """Genera desgloses interpretables y recomendaciones prescriptivas."""
        ...


class AnalyticalStorageProtocol(Protocol):
    """Contrato para motores analiticos OLAP desacoplados (DuckDB / Snowflake)."""
    def execute_query(self, query: str) -> pd.DataFrame:
        """Ejecuta una consulta analitica y retorna un DataFrame en memoria."""
        ...


class TelemetrySinkProtocol(Protocol):
    """Contrato para emision y auditoria de eventos de optimizacion."""
    def persist_optimization_run(self, result: OptimizationAllocationResult) -> None:
        """Registra el resultado de la corrida para trazabilidad y auditoria."""
        ...