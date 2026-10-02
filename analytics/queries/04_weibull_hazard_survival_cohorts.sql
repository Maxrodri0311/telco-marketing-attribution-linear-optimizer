-- ==============================================================================
-- Vonage Marketing Data Science - Weibull Survival Hazard Distribution
-- Target: Snowflake SQL / PostgreSQL 16
-- Mathematical Logic: Kaplan-Meier Non-Parametric & Weibull Continuous Hazard
-- ==============================================================================

WITH discrete_tenure_buckets AS (
    SELECT
        company_tier,
        primary_channel,
        WIDTH_BUCKET(tenure_days, 0.0, 120.0, 12) AS time_bucket_idx,
        (WIDTH_BUCKET(tenure_days, 0.0, 120.0, 12) * 10.0) AS bucket_upper_day,
        COUNT(*) AS total_at_risk,
        SUM(CASE WHEN is_converted THEN 1 ELSE 0 END) AS conversions_in_bucket,
        AVG(hazard_rate) AS empirical_mean_hazard,
        AVG(weibull_shape_k) AS mean_weibull_k,
        AVG(weibull_scale_lambda) AS mean_weibull_lambda
    FROM vonage_marketing_lead_telemetry
    GROUP BY company_tier, primary_channel, WIDTH_BUCKET(tenure_days, 0.0, 120.0, 12)
),
kaplan_meier_progression AS (
    SELECT
        company_tier,
        primary_channel,
        time_bucket_idx,
        bucket_upper_day,
        total_at_risk,
        conversions_in_bucket,
        -- Conditional probability of conversion in bucket
        ROUND(
            (conversions_in_bucket::numeric / NULLIF(total_at_risk, 0)::numeric), 5
        ) AS interval_conversion_rate,
        -- Kaplan-Meier survival factor: p_surv = 1 - (d_i / n_i)
        1.0 - (conversions_in_bucket::numeric / NULLIF(total_at_risk, 0)::numeric) AS interval_survival_factor,
        empirical_mean_hazard,
        mean_weibull_k,
        mean_weibull_lambda
    FROM discrete_tenure_buckets
)
SELECT
    company_tier,
    primary_channel,
    time_bucket_idx,
    bucket_upper_day,
    total_at_risk,
    conversions_in_bucket,
    interval_conversion_rate,
    -- Nelson-Aalen Cumulative Hazard estimate: sum(d_i / n_i)
    ROUND(
        SUM(interval_conversion_rate) OVER (
            PARTITION BY company_tier, primary_channel
            ORDER BY time_bucket_idx
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 4
    ) AS cumulative_hazard_estimate,
    -- Parametric Weibull Cumulative Hazard: H(t) = (t / lambda)^k
    ROUND(
        POWER(bucket_upper_day / NULLIF(mean_weibull_lambda, 0), mean_weibull_k), 4
    ) AS parametric_weibull_cum_hazard,
    ROUND(empirical_mean_hazard, 5) AS instant_hazard_rate
FROM kaplan_meier_progression
ORDER BY company_tier, primary_channel, time_bucket_idx ASC;
