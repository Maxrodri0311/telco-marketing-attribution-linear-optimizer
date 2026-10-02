-- ==============================================================================
-- Vonage Marketing Data Science - Longitudinal Lead Cohort & Survival SQL
-- Target: Snowflake SQL / PostgreSQL 16
-- Features: Multi-Touch Progression, Time-to-Activation & Retention Deciles
-- ==============================================================================

WITH lead_cohort_base AS (
    SELECT
        lead_id,
        company_tier,
        region,
        primary_channel,
        touchpoint_count,
        total_marketing_cost_usd,
        weibull_shape_k,
        weibull_scale_lambda,
        tenure_days,
        hazard_rate,
        survival_probability,
        is_converted,
        activation_ltv_usd,
        -- Ranking de valor por cohorte de canal
        DENSE_RANK() OVER (
            PARTITION BY primary_channel
            ORDER BY activation_ltv_usd DESC
        ) AS channel_ltv_rank,
        -- Segmentación por cuartil de tiempo en el embudo
        NTILE(4) OVER (
            PARTITION BY company_tier
            ORDER BY tenure_days ASC
        ) AS funnel_velocity_quartile,
        -- Promedio móvil de LTV generado por segmento
        AVG(activation_ltv_usd) OVER (
            PARTITION BY company_tier, primary_channel
        ) AS cohort_benchmark_ltv
    FROM vonage_marketing_lead_telemetry
),
cohort_summary AS (
    SELECT
        company_tier,
        primary_channel,
        funnel_velocity_quartile,
        COUNT(lead_id) AS total_leads,
        SUM(CASE WHEN is_converted THEN 1 ELSE 0 END) AS total_conversions,
        ROUND(AVG(total_marketing_cost_usd), 2) AS avg_lead_cost_usd,
        ROUND(AVG(tenure_days), 1) AS avg_days_to_decision,
        ROUND(AVG(hazard_rate), 4) AS mean_hazard_rate,
        ROUND(AVG(survival_probability), 4) AS mean_survival_prob,
        ROUND(SUM(activation_ltv_usd), 2) AS total_realized_ltv_usd,
        ROUND(
            SUM(total_marketing_cost_usd) / NULLIF(SUM(CASE WHEN is_converted THEN 1 ELSE 0 END), 0), 2
        ) AS empirical_cac_usd
    FROM lead_cohort_base
    GROUP BY company_tier, primary_channel, funnel_velocity_quartile
)
SELECT
    company_tier,
    primary_channel,
    funnel_velocity_quartile,
    total_leads,
    total_conversions,
    ROUND((total_conversions::numeric / total_leads::numeric) * 100.0, 2) AS conversion_rate_pct,
    avg_lead_cost_usd,
    avg_days_to_decision,
    mean_hazard_rate,
    mean_survival_prob,
    total_realized_ltv_usd,
    empirical_cac_usd,
    CASE
        WHEN empirical_cac_usd IS NOT NULL AND empirical_cac_usd < 200.0 THEN 'HIGH_EFFICIENCY_ACQUISITION'
        WHEN empirical_cac_usd >= 400.0 THEN 'HIGH_CAC_ATTENTION_REQUIRED'
        ELSE 'STANDARD_PERFORMANCE'
    END AS cohort_efficiency_status
FROM cohort_summary
ORDER BY company_tier, total_realized_ltv_usd DESC;