"""
src/core_engine.py - Core Algorithmic & Optimization Engine for Vonage CPaaS Marketing.
Implements Constrained Linear Programming (SciPy HiGHS) with Dual Shadow Price XAI.
Strictly decoupled via Dependency Inversion Principle (DIP).
"""

import os
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import duckdb
import numpy as np
import pandas as pd
import polars as pl
from scipy.optimize import linprog

# Path resolution for standalone invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.domain.entities import (
    MarketingChannel,
    TargetRegion,
    CompanyTier,
    TouchpointEvent,
    B2BLeadSurvivalProfile,
    ChannelConstraint,
    BudgetOptimizationRequest,
    OptimizationAllocationResult,
    ChannelAttributionExplanation
)
from src.domain.contracts import (
    MarketingDataIngestionProtocol,
    MarketingOptimizationEngineProtocol,
    AttributionExplainerProtocol,
    AnalyticalStorageProtocol,
    TelemetrySinkProtocol,
    ExecutionContext
)


# ============================================================================
# 1. INFRASTRUCTURE ADAPTERS (DIP IMPLEMENTATIONS)
# ============================================================================

class DuckDBStorageAdapter(AnalyticalStorageProtocol):
    """Adaptador de infraestructura desacoplado para OLAP local en memoria."""
    def __init__(self, database: str = ":memory:"):
        self.conn = duckdb.connect(database)

    def execute_query(self, query: str) -> pd.DataFrame:
        return self.conn.execute(query).df()

    def scan_dataset(self, base_path: str) -> pd.DataFrame:
        return self.conn.execute(f"SELECT * FROM read_parquet('{base_path}');").df()


class InMemoryTelemetrySink(TelemetrySinkProtocol):
    """Sink de telemetria en memoria para auditoria y testeo sin I/O de disco."""
    def __init__(self):
        self.audit_log: List[OptimizationAllocationResult] = []

    def persist_optimization_run(self, result: OptimizationAllocationResult) -> None:
        self.audit_log.append(result)


class PolarsMarketingIngestionAdapter(MarketingDataIngestionProtocol):
    """Adaptador de ingesta columnar de alto rendimiento para telemetria de marketing."""
    def load_lead_profiles(self, file_path: str, limit: Optional[int] = None) -> List[B2BLeadSurvivalProfile]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Marketing telemetry parquet not found at {file_path}")

        df = pl.read_parquet(file_path)
        if limit and limit > 0:
            df = df.head(limit)

        profiles: List[B2BLeadSurvivalProfile] = []
        for row in df.iter_rows(named=True):
            profile = B2BLeadSurvivalProfile(
                lead_id=row["lead_id"],
                company_tier=CompanyTier(row["company_tier"]),
                region=TargetRegion(row["region"]),
                weibull_shape_k=float(row["weibull_shape_k"]),
                weibull_scale_lambda=float(row["weibull_scale_lambda"]),
                total_marketing_cost=float(row["total_marketing_cost_usd"]),
                is_converted=bool(row["is_converted"]),
                tenure_days=float(row["tenure_days"]),
                activation_ltv_usd=float(row["activation_ltv_usd"])
            )
            profiles.append(profile)

        return profiles


# ============================================================================
# 2. CORE OPTIMIZATION & XAI ENGINES
# ============================================================================

class VonageMarketingOptimizationEngine(MarketingOptimizationEngineProtocol):
    """
    Motor de Optimizacion Lineal Primal-Dual para Presupuestos de Marketing B2B.
    Maximiza el LTV Total Adquirido sujeto a:
      - Presupuesto Total Trimestral B
      - Techo Estricto de CAC Promedio Blended
      - Cuota Minima de Canales Estrategicos Enterprise (DevRel + Outbound)
      - Cotas de Saturacion y Capacidad por Canal [min_budget, max_budget]
    """
    def solve_budget_allocation(
        self,
        request: BudgetOptimizationRequest,
        historical_leads: Optional[List[B2BLeadSurvivalProfile]] = None
    ) -> OptimizationAllocationResult:
        start_time = time.perf_counter()
        constraints = request.channel_constraints
        channels = [c.channel for c in constraints]
        n_channels = len(channels)

        # 1. Vector de Costos Objetivo (Minimizamos -LTV Multiplier para Maximizar LTV)
        # c_obj[i] = - expected_ltv_multiplier_i
        c_obj = np.array([-c.expected_ltv_multiplier for c in constraints], dtype=np.float64)

        # 2. Matriz de Restricciones Desiguales A_ub * x <= b_ub
        # Restriccion 1: Presupuesto Total sum(x_i) <= total_budget
        # Restriccion 2: Blended CAC <= max_blended_cac_target
        #   CAC_blended = sum(x_i) / sum(x_i / cac_i) <= CAC_target
        #   <=> sum(x_i * (1 - CAC_target / cac_i)) <= 0
        # Restriccion 3: Cuota Minima Enterprise (Outbound + Partner >= quota * B)
        #   <=> - sum_{ent}(x_i) <= - quota * B
        A_ub_rows = []
        b_ub_rows = []

        # R1: Presupuesto Total
        A_ub_rows.append(np.ones(n_channels, dtype=np.float64))
        b_ub_rows.append(request.total_budget_usd)

        # R2: Blended CAC Limit
        cac_coeffs = np.array([
            (1.0 - (request.max_blended_cac_target / c.historical_cac))
            for c in constraints
        ], dtype=np.float64)
        A_ub_rows.append(cac_coeffs)
        b_ub_rows.append(0.0)

        # R3: Cuota Minima Enterprise (Outbound + Partner)
        ent_indicator = np.array([
            -1.0 if c.channel in [MarketingChannel.TARGETED_OUTBOUND, MarketingChannel.PARTNER_ECOSYSTEM] else 0.0
            for c in constraints
        ], dtype=np.float64)
        min_ent_budget = request.total_budget_usd * request.minimum_enterprise_allocation_pct
        A_ub_rows.append(ent_indicator)
        b_ub_rows.append(-min_ent_budget)

        A_ub = np.vstack(A_ub_rows)
        b_ub = np.array(b_ub_rows, dtype=np.float64)

        # 3. Cotas por Canal [min_budget, max_budget]
        bounds = [(c.min_budget_usd, c.max_budget_usd) for c in constraints]

        # 4. Resolucion Primal-Dual via SciPy HiGHS Simplex
        res = linprog(
            c=c_obj,
            A_ub=A_ub,
            b_ub=b_ub,
            bounds=bounds,
            method="highs"
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if not res.success:
            # Fallback en caso de incompatibilidad estricta
            allocations = {c.channel: c.min_budget_usd for c in constraints}
            return OptimizationAllocationResult(
                run_id=f"RUN-{uuid.uuid4().hex[:8].upper()}",
                is_optimal=False,
                solver_status_code=int(res.status),
                solver_latency_ms=latency_ms,
                total_budget_allocated=float(sum(allocations.values())),
                allocations_by_channel=allocations,
                expected_total_conversions=0.0,
                expected_blended_cac=0.0,
                expected_total_ltv=0.0,
                dual_shadow_prices={c.channel: 0.0 for c in constraints},
                budget_utilization_pct=0.0
            )

        # 5. Extraccion de Resultados Primals y Precios Sombra Duales
        allocations: Dict[MarketingChannel, float] = {}
        total_allocated = float(np.sum(res.x))
        expected_conversions = 0.0
        expected_ltv = 0.0

        for i, c in enumerate(constraints):
            allocated_usd = float(res.x[i])
            allocations[c.channel] = np.round(allocated_usd, 2)
            conv_i = allocated_usd / c.historical_cac
            expected_conversions += conv_i
            expected_ltv += allocated_usd * c.expected_ltv_multiplier

        blended_cac = (total_allocated / expected_conversions) if expected_conversions > 0 else 0.0
        utilization_pct = (total_allocated / request.total_budget_usd) * 100.0

        # Precios Sombra Duales (Marginal LTV Gain per dollar)
        # res.ineqlin.marginals indica la sensibilidad marginal de cada restriccion
        dual_shadows: Dict[MarketingChannel, float] = {}
        budget_shadow_price = float(abs(res.ineqlin.marginals[0])) if hasattr(res, "ineqlin") and len(res.ineqlin.marginals) > 0 else 1.0

        for i, c in enumerate(constraints):
            # El shadow price refleja el multiplicador neto marginal menos el costo dual del presupuesto
            marginal_val = float(c.expected_ltv_multiplier - budget_shadow_price)
            dual_shadows[c.channel] = np.round(max(marginal_val, 0.0), 4)

        return OptimizationAllocationResult(
            run_id=f"RUN-{uuid.uuid4().hex[:8].upper()}",
            is_optimal=True,
            solver_status_code=int(res.status),
            solver_latency_ms=latency_ms,
            total_budget_allocated=np.round(total_allocated, 2),
            allocations_by_channel=allocations,
            expected_total_conversions=np.round(expected_conversions, 2),
            expected_blended_cac=np.round(blended_cac, 2),
            expected_total_ltv=np.round(expected_ltv, 2),
            dual_shadow_prices=dual_shadows,
            budget_utilization_pct=np.round(utilization_pct, 2)
        )


class VonageAttributionExplainer(AttributionExplainerProtocol):
    """Generador de Explicabilidad XAI para Directores de Marketing y C-Level."""
    def explain_allocations(
        self,
        result: OptimizationAllocationResult,
        request: BudgetOptimizationRequest
    ) -> List[ChannelAttributionExplanation]:
        explanations: List[ChannelAttributionExplanation] = []
        constraint_map = {c.channel: c for c in request.channel_constraints}
        total_alloc = max(result.total_budget_allocated, 1.0)
        total_ltv = max(result.expected_total_ltv, 1.0)

        for channel, alloc_usd in result.allocations_by_channel.items():
            c = constraint_map[channel]
            share_pct = (alloc_usd / total_alloc) * 100.0
            channel_ltv = alloc_usd * c.expected_ltv_multiplier
            attr_weight = (channel_ltv / total_ltv) * 100.0
            dual_price = result.dual_shadow_prices.get(channel, 0.0)

            # Recomendación accionable prescriptiva
            if alloc_usd >= c.max_budget_usd * 0.95:
                rec = "Canal en saturacion optima; aumentar techo presupuestario en Q+1 para capturar LTV adicional."
            elif alloc_usd <= c.min_budget_usd * 1.05:
                rec = "Canal en cota minima obligatoria; bajo retorno marginal relativo frente a otros canales."
            else:
                rec = "Asignacion balanceada; opera en punto dulce de eficiencia de CAC y conversion."

            explanations.append(ChannelAttributionExplanation(
                channel=channel,
                allocated_usd=alloc_usd,
                budget_share_pct=np.round(share_pct, 2),
                marginal_ltv_per_dollar=np.round(c.expected_ltv_multiplier, 2),
                dual_shadow_price=dual_price,
                attribution_weight_pct=np.round(attr_weight, 2),
                recommendation=rec
            ))

        return explanations


class OptimizationComparisonService:
    """Servicio comparativo: Programacion Lineal Restringida vs Heuristica Proporcional Estatica."""
    @staticmethod
    def compare_lp_vs_heuristic(
        request: BudgetOptimizationRequest,
        result_lp: OptimizationAllocationResult
    ) -> Dict[str, Any]:
        constraints = request.channel_constraints
        total_budget = request.total_budget_usd

        # Heuristica Estatica: Distribución Uniforme o Proporcional a Límites Máximos
        max_sum = sum(c.max_budget_usd for c in constraints)
        heuristic_allocs = {
            c.channel: np.round((c.max_budget_usd / max_sum) * total_budget, 2)
            for c in constraints
        }
        heuristic_conversions = sum(
            heuristic_allocs[c.channel] / c.historical_cac for c in constraints
        )
        heuristic_ltv = sum(
            heuristic_allocs[c.channel] * c.expected_ltv_multiplier for c in constraints
        )
        heuristic_cac = total_budget / heuristic_conversions if heuristic_conversions > 0 else 0.0

        ltv_uplift_pct = ((result_lp.expected_total_ltv - heuristic_ltv) / heuristic_ltv) * 100.0
        cac_reduction_pct = ((heuristic_cac - result_lp.expected_blended_cac) / heuristic_cac) * 100.0

        return {
            "lp_expected_ltv": result_lp.expected_total_ltv,
            "heuristic_expected_ltv": np.round(heuristic_ltv, 2),
            "net_ltv_gain_usd": np.round(result_lp.expected_total_ltv - heuristic_ltv, 2),
            "ltv_uplift_pct": np.round(ltv_uplift_pct, 2),
            "lp_blended_cac": result_lp.expected_blended_cac,
            "heuristic_blended_cac": np.round(heuristic_cac, 2),
            "cac_reduction_pct": np.round(cac_reduction_pct, 2),
            "cac_target_respected_lp": result_lp.expected_blended_cac <= request.max_blended_cac_target,
            "cac_target_respected_heuristic": heuristic_cac <= request.max_blended_cac_target
        }


# ============================================================================
# 3. BACKWARD COMPATIBLE DOMAIN ANALYTICS ENGINE (TEST SUITE SUPPORT)
# ============================================================================

class DomainAnalyticsEngine:
    """Clase analitica compatible para soporte de fixtures de pruebas heredadas."""
    def __init__(
        self,
        storage: AnalyticalStorageProtocol,
        data_path: str = "data/raw_dataset.parquet",
    ):
        self.storage = storage
        self.data_path = data_path

    def execute_analysis(self) -> pd.DataFrame:
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Dataset not found at {self.data_path}")

        query = f"""
            SELECT 
                COUNT(*) as total_records,
                ROUND(AVG(total_marketing_cost_usd), 4) as mean_primary_metric,
                ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_marketing_cost_usd), 4) as p95_metric,
                ROUND(MIN(total_marketing_cost_usd), 4) as min_metric,
                ROUND(MAX(total_marketing_cost_usd), 4) as max_metric
            FROM read_parquet('{self.data_path}');
        """
        return self.storage.execute_query(query)


def create_engine(data_path: str = "data/raw_dataset.parquet") -> DomainAnalyticsEngine:
    adapter = DuckDBStorageAdapter()
    return DomainAnalyticsEngine(storage=adapter, data_path=data_path)


# ============================================================================
# 4. DEFAULT COMPOSITION ROOT FOR MARKETING OPTIMIZATION
# ============================================================================

def create_default_optimization_request(total_budget: float = 2500000.0) -> BudgetOptimizationRequest:
    """Genera la especificacion de presupuesto predeterminada de Vonage CPaaS."""
    constraints = [
        ChannelConstraint(
            channel=MarketingChannel.DEVREL_HACKATHONS,
            min_budget_usd=250000.0,
            max_budget_usd=800000.0,
            historical_cac=180.0,
            expected_ltv_multiplier=14.2
        ),
        ChannelConstraint(
            channel=MarketingChannel.PAID_SEARCH_CORE,
            min_budget_usd=300000.0,
            max_budget_usd=750000.0,
            historical_cac=220.0,
            expected_ltv_multiplier=9.8
        ),
        ChannelConstraint(
            channel=MarketingChannel.CONTENT_SEO_TECHNICAL,
            min_budget_usd=150000.0,
            max_budget_usd=600000.0,
            historical_cac=95.0,
            expected_ltv_multiplier=12.5
        ),
        ChannelConstraint(
            channel=MarketingChannel.TARGETED_OUTBOUND,
            min_budget_usd=350000.0,
            max_budget_usd=900000.0,
            historical_cac=480.0,
            expected_ltv_multiplier=16.8
        ),
        ChannelConstraint(
            channel=MarketingChannel.PROGRAMMATIC_DISPLAY,
            min_budget_usd=50000.0,
            max_budget_usd=300000.0,
            historical_cac=310.0,
            expected_ltv_multiplier=4.2
        ),
        ChannelConstraint(
            channel=MarketingChannel.PARTNER_ECOSYSTEM,
            min_budget_usd=200000.0,
            max_budget_usd=650000.0,
            historical_cac=290.0,
            expected_ltv_multiplier=15.1
        )
    ]
    return BudgetOptimizationRequest(
        total_budget_usd=total_budget,
        max_blended_cac_target=225.0,
        channel_constraints=constraints,
        minimum_enterprise_allocation_pct=0.25
    )


if __name__ == "__main__":
    from src.data_generator import generate_domain_dataset

    path = "data/raw_dataset.parquet"
    if not os.path.exists(path):
        print(f"[Core Engine] Bootstrapping telemetry dataset at {path}...")
        generate_domain_dataset(num_records=10000, output_path=path)

    request = create_default_optimization_request(total_budget=2500000.0)
    engine = VonageMarketingOptimizationEngine()
    result = engine.solve_budget_allocation(request=request)

    explainer = VonageAttributionExplainer()
    explanations = explainer.explain_allocations(result=result, request=request)
    comparison = OptimizationComparisonService.compare_lp_vs_heuristic(request, result)

    print("\n" + "=" * 80)
    print("  VONAGE CPaaS: B2B MARKETING ATTRIBUTION & LINEAR PROGRAMMING SOLVER (HiGHS)")
    print("=" * 80)
    print(f" Run ID                     : {result.run_id}")
    print(f" Solver Optimal             : {result.is_optimal} (Status: {result.solver_status_code})")
    print(f" Solver Latency             : {result.solver_latency_ms:.2f} ms")
    print(f" Total Budget Allocated     : ${result.total_budget_allocated:,.2f} ({result.budget_utilization_pct:.1f}% util)")
    print(f" Expected Converted Leads   : {result.expected_total_conversions:,.1f} accounts")
    print(f" Blended CAC Achieved       : ${result.expected_blended_cac:.2f} (Target: <${request.max_blended_cac_target:.2f})")
    print(f" Total Expected LTV Acquired: ${result.expected_total_ltv:,.2f}")
    print("-" * 80)
    print(" CHANNEL ALLOCATIONS & XAI ATTRIBUTION EXPLANATIONS:")
    print(f" {'Channel':<26} | {'Budget ($)':<12} | {'Share':<6} | {'Dual Shadow':<12} | {'Action'}")
    print("-" * 80)
    for exp in explanations:
        print(f" {exp.channel.value:<26} | ${exp.allocated_usd:>10,.2f} | {exp.budget_share_pct:>5.1f}% | ${exp.dual_shadow_price:>10.4f} | {exp.recommendation[:30]}...")
    print("-" * 80)
    print(" COMPARISON: CONSTRAINED LINEAR PROGRAMMING VS STATIC HEURISTIC")
    print(f" -> LTV Net Gain            : +${comparison['net_ltv_gain_usd']:,.2f} (+{comparison['ltv_uplift_pct']}%)")
    print(f" -> CAC Reduction           : -{comparison['cac_reduction_pct']}% (${result.expected_blended_cac:.2f} vs ${comparison['heuristic_blended_cac']:.2f})")
    print(f" -> CAC Target Respected    : LP: {comparison['cac_target_respected_lp']} | Heuristic: {comparison['cac_target_respected_heuristic']}")
    print("=" * 80 + "\n")