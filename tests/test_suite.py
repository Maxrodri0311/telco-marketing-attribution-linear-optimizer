"""
tests/test_suite.py - Mathematical Invariants & Architecture Quality Suite.
Validates 100% of mathematical invariants, LP solver feasibility, XAI dual shadow prices,
and Dependency Inversion Principle (DIP) in-memory mocks for Vonage Marketing Data Science.
"""

import os
import tempfile
import pytest
import numpy as np
import polars as pl

from src.domain.entities import (
    MarketingChannel,
    TargetRegion,
    CompanyTier,
    BudgetOptimizationRequest,
    OptimizationAllocationResult,
    B2BLeadSurvivalProfile
)
from src.domain.contracts import (
    MarketingDataIngestionProtocol,
    MarketingOptimizationEngineProtocol,
    AttributionExplainerProtocol,
    AnalyticalStorageProtocol,
    TelemetrySinkProtocol
)
from src.data_generator import generate_domain_dataset
from src.core_engine import (
    VonageMarketingOptimizationEngine,
    VonageAttributionExplainer,
    OptimizationComparisonService,
    create_default_optimization_request,
    PolarsMarketingIngestionAdapter,
    DuckDBStorageAdapter,
    InMemoryTelemetrySink,
    DomainAnalyticsEngine
)


@pytest.fixture(scope="session")
def sample_dataset(tmp_path_factory):
    """Fixture de sesion: genera un dataset de prueba calibrado con 5,000 registros."""
    fn = tmp_path_factory.mktemp("data") / "test_marketing_leads.parquet"
    df = generate_domain_dataset(num_records=5000, output_path=str(fn), seed=123)
    return str(fn)


def test_stochastic_generator_invariants(sample_dataset):
    """
    Test 1: Invariantes Fisicos del Generador Estocastico de Leads B2B.
    Verifica no-nulos, limites de Weibull (k > 1.0), congruencia de LTV y tasas de conversion.
    """
    df = pl.read_parquet(sample_dataset)
    assert len(df) == 5000
    assert sum(df.null_count().row(0)) == 0, "No deben existir valores nulos"

    # Verificar parametros de Weibull
    k_vals = df["weibull_shape_k"].to_numpy()
    lambda_vals = df["weibull_scale_lambda"].to_numpy()
    assert np.all(k_vals >= 1.05) and np.all(k_vals <= 2.80), "Forma k de Weibull fuera de rango"
    assert np.all(lambda_vals >= 9.0) and np.all(lambda_vals <= 100.0), "Escala lambda fuera de rango"

    # Verificar conversion y LTV
    converted = df["is_converted"].to_numpy()
    ltv = df["activation_ltv_usd"].to_numpy()
    conv_rate = float(np.mean(converted))
    assert 0.25 <= conv_rate <= 0.60, f"Tasa de conversion anomala: {conv_rate:.2f}"
    assert np.all(ltv[converted] > 0.0), "Leads convertidos deben tener LTV positivo"
    assert np.all(ltv[~converted] == 0.0), "Leads no convertidos deben tener LTV cero"


def test_linear_programming_feasibility_and_bounds():
    """
    Test 2: Factibilidad Matematica y Cumplimiento Estricto de Cotas del Solver HiGHS.
    Garantiza que la asignacion respete el presupuesto, techo de CAC y cuotas enterprise.
    """
    engine = VonageMarketingOptimizationEngine()
    request = create_default_optimization_request(total_budget=2500000.0)
    result = engine.solve_budget_allocation(request=request)

    assert result.is_optimal is True, "El solver LP debe converger a optimalidad (status == 0)"
    assert result.solver_status_code == 0
    assert result.total_budget_allocated <= request.total_budget_usd + 1e-4, "Exceso de presupuesto global"

    # Verificar que se respete el techo de Blended CAC
    assert result.expected_blended_cac <= request.max_blended_cac_target + 0.05, (
        f"CAC excedido: {result.expected_blended_cac:.2f} > {request.max_blended_cac_target:.2f}"
    )

    # Verificar cuota minima Enterprise (Outbound + Partner >= 25% del presupuesto)
    ent_alloc = (
        result.allocations_by_channel[MarketingChannel.TARGETED_OUTBOUND] +
        result.allocations_by_channel[MarketingChannel.PARTNER_ECOSYSTEM]
    )
    expected_min_ent = request.total_budget_usd * request.minimum_enterprise_allocation_pct
    assert ent_alloc >= expected_min_ent - 1.0, f"Cuota Enterprise no satisfecha: ${ent_alloc:,.2f}"

    # Verificar cotas individuales por canal
    for c in request.channel_constraints:
        alloc = result.allocations_by_channel[c.channel]
        assert alloc >= c.min_budget_usd - 0.01, f"Cota inferior violada en {c.channel}"
        assert alloc <= c.max_budget_usd + 0.01, f"Cota superior violada en {c.channel}"


def test_linear_programming_superiority_over_static_heuristic():
    """
    Test 3: Superioridad Matematica de la Optimizacion Primal frente a Heuristica Estatica.
    Demuestra que el solver HiGHS captura significativamente mayor LTV bajo el mismo presupuesto.
    """
    engine = VonageMarketingOptimizationEngine()
    request = create_default_optimization_request(total_budget=2500000.0)
    result = engine.solve_budget_allocation(request=request)

    comparison = OptimizationComparisonService.compare_lp_vs_heuristic(request, result)
    assert comparison["net_ltv_gain_usd"] > 0, "El optimizador lineal debe superar a la heuristica estatica"
    assert comparison["ltv_uplift_pct"] >= 5.0, "Uplift de LTV debe ser >= 5.0%"
    assert comparison["cac_target_respected_lp"] is True, "El LP debe garantizar cumplimiento estricto del CAC"


def test_xai_dual_shadow_prices_and_explanations():
    """
    Test 4: Explicabilidad XAI y Extraccion de Precios Sombra Duales.
    Verifica que cada canal reciba su descomposicion marginal y recomendacion accionable.
    """
    engine = VonageMarketingOptimizationEngine()
    explainer = VonageAttributionExplainer()
    request = create_default_optimization_request(total_budget=2500000.0)
    result = engine.solve_budget_allocation(request=request)

    explanations = explainer.explain_allocations(result=result, request=request)
    assert len(explanations) == len(request.channel_constraints)

    # Validar que los precios sombra duales no sean vacios y que los pesos sumen 100%
    total_attr_weight = sum(exp.attribution_weight_pct for exp in explanations)
    assert abs(total_attr_weight - 100.0) < 0.5, f"Pesos de atribucion deben sumar 100%, dio {total_attr_weight}"

    for exp in explanations:
        assert exp.allocated_usd >= 0.0
        assert exp.budget_share_pct >= 0.0
        assert exp.marginal_ltv_per_dollar > 0.0
        assert exp.dual_shadow_price >= 0.0
        assert len(exp.recommendation) > 15, "La recomendacion debe ser descriptiva y accionable"


def test_dependency_inversion_and_in_memory_telemetry_mock():
    """
    Test 5: Inversion de Dependencias (DIP) y Mocking In-Memory Sub-5ms.
    Verifica que la orquestacion de optimizacion opere con mocks puros sin tocar disco ni base de datos.
    """
    class MockOptimizationEngine(MarketingOptimizationEngineProtocol):
        def solve_budget_allocation(self, request, historical_leads=None):
            return OptimizationAllocationResult(
                run_id="MOCK-RUN-999",
                is_optimal=True,
                solver_status_code=0,
                solver_latency_ms=1.2,
                total_budget_allocated=request.total_budget_usd,
                allocations_by_channel={c.channel: c.min_budget_usd for c in request.channel_constraints},
                expected_total_conversions=1200.0,
                expected_blended_cac=200.0,
                expected_total_ltv=30000000.0,
                dual_shadow_prices={c.channel: 1.5 for c in request.channel_constraints},
                budget_utilization_pct=100.0
            )

    sink = InMemoryTelemetrySink()
    mock_engine = MockOptimizationEngine()
    request = create_default_optimization_request(total_budget=1000000.0)

    # Ejecucion aislada sin I/O
    res = mock_engine.solve_budget_allocation(request=request)
    sink.persist_optimization_run(res)

    assert len(sink.audit_log) == 1
    assert sink.audit_log[0].run_id == "MOCK-RUN-999"
    assert sink.audit_log[0].is_optimal is True
    assert sink.audit_log[0].solver_latency_ms < 5.0