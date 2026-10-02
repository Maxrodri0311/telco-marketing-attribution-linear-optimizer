"""
src/interface.py - FastAPI Microservice & OpenAPI Engine (EXPLAINABLE_AI_INFERENCE Paradigm).
Inference, Linear Optimization, and XAI Marginal Attribution API for Vonage CPaaS.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.domain.entities import (
    MarketingChannel,
    TargetRegion,
    CompanyTier,
    ChannelConstraint,
    BudgetOptimizationRequest,
    OptimizationAllocationResult,
    ChannelAttributionExplanation
)
from src.core_engine import (
    VonageMarketingOptimizationEngine,
    VonageAttributionExplainer,
    OptimizationComparisonService,
    create_default_optimization_request,
    create_engine
)

app = FastAPI(
    title="Vonage CPaaS: B2B Marketing Attribution & XAI Optimization Engine",
    description=(
        "Enterprise decision support API powered by Constrained Linear Programming (SciPy HiGHS) "
        "and Weibull Survival Analytics. Optimizes multi-channel quarterly marketing budget allocation "
        "to maximize acquired Customer Lifetime Value (LTV) while enforcing strict Blended CAC ceilings "
        "and extracting Dual Shadow Prices for C-Level explainability."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Composition roots
engine = VonageMarketingOptimizationEngine()
explainer = VonageAttributionExplainer()


# ============================================================================
# API CONTRACTS & SCHEMAS
# ============================================================================

class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "vonage-marketing-attribution-engine"
    version: str = "1.0.0"
    paradigm: str = "EXPLAINABLE_AI_INFERENCE"


class HazardCurvePoint(BaseModel):
    tenure_days: float
    hazard_rate: float
    survival_probability: float


class SurvivalCurveResponse(BaseModel):
    company_tier: str
    weibull_shape_k: float
    weibull_scale_lambda: float
    curve: List[HazardCurvePoint]


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Healthcheck probe for container orchestrators"
)
def health_check():
    """Liveness probe validating microservice operational readiness."""
    return HealthResponse()


@app.post(
    "/api/v1/optimization/allocate",
    response_model=OptimizationAllocationResult,
    status_code=status.HTTP_200_OK,
    tags=["Optimization"],
    summary="Execute primal-dual linear programming budget allocation"
)
def solve_budget_allocation(request: Optional[BudgetOptimizationRequest] = None):
    """
    Solves the constrained primal optimization problem via SciPy HiGHS Simplex.
    Maximizes expected LTV subject to:
      1. Total budget cap B
      2. Maximum blended CAC threshold
      3. Enterprise strategic channel quota (>= 25%)
      4. Channel saturation upper/lower bounds
    """
    req = request or create_default_optimization_request()
    try:
        result = engine.solve_budget_allocation(request=req)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Solver execution error: {str(e)}"
        )


@app.post(
    "/api/v1/attribution/explain",
    response_model=List[ChannelAttributionExplanation],
    status_code=status.HTTP_200_OK,
    tags=["Explainability"],
    summary="Extract XAI attribution weights and dual shadow prices"
)
def explain_marketing_attribution(request: Optional[BudgetOptimizationRequest] = None):
    """
    Returns channel-level marginal ROI explanations, budget shares, and Dual Shadow Prices.
    Shadow prices indicate the marginal LTV yield of expanding a channel's budget ceiling by $1.00 USD.
    """
    req = request or create_default_optimization_request()
    try:
        result = engine.solve_budget_allocation(request=req)
        explanations = explainer.explain_allocations(result=result, request=req)
        return explanations
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Attribution explainer error: {str(e)}"
        )


@app.get(
    "/api/v1/comparison/benchmark",
    response_model=Dict[str, Any],
    tags=["Optimization"],
    summary="Benchmark LP optimal allocation vs static proportional heuristic"
)
def compare_lp_vs_heuristic(total_budget: float = 2500000.0):
    """
    Computes financial variance, LTV net uplift, and CAC compliance between
    constrained Linear Programming and traditional static proportional triage.
    """
    req = create_default_optimization_request(total_budget=total_budget)
    result = engine.solve_budget_allocation(request=req)
    comparison = OptimizationComparisonService.compare_lp_vs_heuristic(req, result)
    return comparison


@app.get(
    "/api/v1/survival/hazard-curve",
    response_model=List[SurvivalCurveResponse],
    tags=["Survival Analytics"],
    summary="Retrieve calibrated Weibull hazard and survival curves by company tier"
)
def get_survival_curves():
    """
    Returns parametric Weibull lifecycle curves:
    h(t) = (k/lambda) * (t/lambda)^(k-1) and S(t) = exp(-(t/lambda)^k)
    across Startup, Mid-Market, and Strategic Enterprise tiers.
    """
    tiers_params = [
        ("STARTUP_DEVELOPER", 1.45, 21.0),
        ("MID_MARKET_GROWTH", 1.85, 45.0),
        ("ENTERPRISE_STRATEGIC", 2.30, 75.0)
    ]
    time_points = [1.0, 7.0, 14.0, 21.0, 30.0, 45.0, 60.0, 90.0]
    responses: List[SurvivalCurveResponse] = []

    import math
    for tier_name, k, lam in tiers_params:
        curve_pts: List[HazardCurvePoint] = []
        for t in time_points:
            h = (k / lam) * ((t / lam) ** (k - 1))
            s = math.exp(-((t / lam) ** k))
            curve_pts.append(HazardCurvePoint(
                tenure_days=t,
                hazard_rate=round(h, 5),
                survival_probability=round(s, 4)
            ))
        responses.append(SurvivalCurveResponse(
            company_tier=tier_name,
            weibull_shape_k=k,
            weibull_scale_lambda=lam,
            curve=curve_pts
        ))

    return responses


@app.get(
    "/api/v1/telemetry/summary",
    tags=["Analytics"],
    summary="Execute backward-compatible columnar summary analysis via DuckDB"
)
def get_telemetry_summary():
    """Executes vectorized aggregation over local Parquet storage."""
    try:
        analytics_engine = create_engine()
        df = analytics_engine.execute_analysis()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DuckDB aggregation error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)