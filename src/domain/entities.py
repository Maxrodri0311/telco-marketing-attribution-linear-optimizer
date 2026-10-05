"""
src/domain/entities.py - Modelos de Dominio Puros para Telecom & Cloud Communications Practice Marketing Data Science.
Estructuras inmutables y tipadas para Atribucion Multi-Touch, Supervivencia B2B y Optimizacion Lineal.
Cero dependencias externas de I/O o persistencia (Regla DIP).
"""

from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class MarketingChannel(str, Enum):
    DEVREL_HACKATHONS = "DEVREL_HACKATHONS"
    PAID_SEARCH_CORE = "PAID_SEARCH_CORE"
    CONTENT_SEO_TECHNICAL = "CONTENT_SEO_TECHNICAL"
    TARGETED_OUTBOUND = "TARGETED_OUTBOUND"
    PROGRAMMATIC_DISPLAY = "PROGRAMMATIC_DISPLAY"
    PARTNER_ECOSYSTEM = "PARTNER_ECOSYSTEM"


class TargetRegion(str, Enum):
    NORTH_AMERICA = "NORTH_AMERICA"
    EMEA = "EMEA"
    APAC = "APAC"
    LATAM = "LATAM"


class CompanyTier(str, Enum):
    STARTUP_DEVELOPER = "STARTUP_DEVELOPER"
    MID_MARKET_GROWTH = "MID_MARKET_GROWTH"
    ENTERPRISE_STRATEGIC = "ENTERPRISE_STRATEGIC"


class TouchpointEvent(BaseModel):
    """Evento individual de interaccion publicitaria o tecnica en el embudo."""
    model_config = ConfigDict(frozen=True)

    lead_id: str
    channel: MarketingChannel
    cost_usd: float = Field(ge=0.0)
    touch_order: int = Field(ge=1)
    days_since_first_touch: float = Field(ge=0.0)
    engagement_depth_score: float = Field(ge=0.0, le=1.0)


class B2BLeadSurvivalProfile(BaseModel):
    """Perfil longitudinal de lead B2B con dinamica de supervivencia de Weibull."""
    model_config = ConfigDict(frozen=True)

    lead_id: str
    company_tier: CompanyTier
    region: TargetRegion
    touchpoints: List[TouchpointEvent] = Field(default_factory=list)
    weibull_shape_k: float = Field(gt=0.0, description="Parametro de forma Weibull (k > 1 indica fatiga/aceleracion)")
    weibull_scale_lambda: float = Field(gt=0.0, description="Parametro de escala temporal en dias")
    total_marketing_cost: float = Field(ge=0.0)
    is_converted: bool = False
    tenure_days: float = Field(ge=0.0)
    activation_ltv_usd: float = Field(ge=0.0)

    @property
    def hazard_rate(self) -> float:
        """Tasa instantanea de conversion/activacion h(t)."""
        t = max(self.tenure_days, 0.01)
        k = self.weibull_shape_k
        lam = self.weibull_scale_lambda
        return (k / lam) * ((t / lam) ** (k - 1))

    @property
    def survival_probability(self) -> float:
        """Probabilidad de no activacion hasta el tiempo t: S(t) = exp(-(t/lambda)^k)."""
        t = max(self.tenure_days, 0.0)
        k = self.weibull_shape_k
        lam = self.weibull_scale_lambda
        import math
        return math.exp(-((t / lam) ** k))


class ChannelConstraint(BaseModel):
    """Restricciones operativas y de saturacion de canal publicitario."""
    model_config = ConfigDict(frozen=True)

    channel: MarketingChannel
    min_budget_usd: float = Field(ge=0.0)
    max_budget_usd: float = Field(gt=0.0)
    historical_cac: float = Field(gt=0.0)
    expected_ltv_multiplier: float = Field(gt=0.0)


class BudgetOptimizationRequest(BaseModel):
    """Especificacion del problema primal de asignacion de presupuesto trimestral."""
    model_config = ConfigDict(frozen=True)

    total_budget_usd: float = Field(gt=0.0)
    max_blended_cac_target: float = Field(gt=0.0)
    channel_constraints: List[ChannelConstraint]
    minimum_enterprise_allocation_pct: float = Field(default=0.20, ge=0.0, le=1.0)


class OptimizationAllocationResult(BaseModel):
    """Resultado de resolucion de programacion lineal (SciPy HiGHS)."""
    model_config = ConfigDict(frozen=True)

    run_id: str
    is_optimal: bool
    solver_status_code: int
    solver_latency_ms: float
    total_budget_allocated: float
    allocations_by_channel: Dict[MarketingChannel, float]
    expected_total_conversions: float
    expected_blended_cac: float
    expected_total_ltv: float
    dual_shadow_prices: Dict[MarketingChannel, float]
    budget_utilization_pct: float


class ChannelAttributionExplanation(BaseModel):
    """Explicacion XAI interpretable para directores de marketing y comites C-Level."""
    model_config = ConfigDict(frozen=True)

    channel: MarketingChannel
    allocated_usd: float
    budget_share_pct: float
    marginal_ltv_per_dollar: float
    dual_shadow_price: float
    attribution_weight_pct: float
    recommendation: str