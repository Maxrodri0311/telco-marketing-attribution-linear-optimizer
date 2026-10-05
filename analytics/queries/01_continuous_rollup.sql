-- ==============================================================================
-- Telecom & Cloud Communications Practice Marketing Analytics - Continuous Statistical Rollup Mart
-- Target: PostgreSQL 16 Materialized Views & Statistical Windowing
-- Role: Marketing Data Scientist
-- Features: 7d Rolling CAC Velocity, Conversion Deciles & Multi-Channel ROI
-- ==============================================================================

SET search_path TO marketing_analytics, public;

DROP MATERIALIZED VIEW IF EXISTS mv_vonage_marketing_continuous_rollup CASCADE;

CREATE MATERIALIZED VIEW mv_vonage_marketing_continuous_rollup AS
WITH daily_channel_slices AS (
    SELECT
        primary_channel,
        company_tier,
        region,
        DATE_TRUNC('day', event_timestamp) AS observation_day,
        COUNT(*) AS total_leads_touched,
        COUNT(CASE WHEN is_converted THEN 1 END) AS converted_leads,
        SUM(total_marketing_cost_usd) AS daily_spend_usd,
        SUM(activation_ltv_usd) AS daily_ltv_generated
    FROM vonage_marketing_lead_telemetry
    GROUP BY primary_channel, company_tier, region, DATE_TRUNC('day', event_timestamp)
),
windowed_acceleration AS (
    SELECT
        primary_channel,
        company_tier,
        region,
        observation_day,
        total_leads_touched,
        converted_leads,
        daily_spend_usd,
        daily_ltv_generated,
        -- Rolling 7-day spend and conversion aggregation
        SUM(daily_spend_usd) OVER (
            PARTITION BY primary_channel, company_tier
            ORDER BY observation_day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_spend_usd,
        SUM(converted_leads) OVER (
            PARTITION BY primary_channel, company_tier
            ORDER BY observation_day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_conversions,
        -- Lagged daily metrics
        LAG(daily_spend_usd, 1) OVER (
            PARTITION BY primary_channel, company_tier ORDER BY observation_day
        ) AS prev_day_spend_usd,
        -- Decile segmentation based on LTV efficiency
        NTILE(10) OVER (
            PARTITION BY observation_day
            ORDER BY daily_ltv_generated DESC
        ) AS ltv_efficiency_decile
    FROM daily_channel_slices
)
SELECT
    primary_channel,
    company_tier,
    region,
    observation_day,
    total_leads_touched,
    converted_leads,
    daily_spend_usd,
    daily_ltv_generated,
    ROUND(rolling_7d_spend_usd, 2) AS rolling_7d_spend_usd,
    rolling_7d_conversions,
    -- Effective Blended Rolling CAC
    ROUND(
        CASE 
            WHEN rolling_7d_conversions > 0 
            THEN rolling_7d_spend_usd / rolling_7d_conversions 
            ELSE rolling_7d_spend_usd 
        END, 2
    ) AS rolling_7d_blended_cac,
    ltv_efficiency_decile,
    CASE 
        WHEN ltv_efficiency_decile <= 2 THEN 'TOP_PERFORMING_EFFICIENCY'
        WHEN rolling_7d_conversions = 0 THEN 'CAC_SURGE_WARNING'
        ELSE 'STABLE_CHANNEL'
    END AS operational_channel_status,
    CURRENT_TIMESTAMP AS mart_refreshed_at
FROM windowed_acceleration;

CREATE UNIQUE INDEX IF NOT EXISTS uq_idx_vonage_marketing_rollup_day 
    ON mv_vonage_marketing_continuous_rollup (primary_channel, company_tier, region, observation_day);

CREATE INDEX IF NOT EXISTS idx_vonage_marketing_rollup_status 
    ON mv_vonage_marketing_continuous_rollup (operational_channel_status, ltv_efficiency_decile);

COMMENT ON MATERIALIZED VIEW mv_vonage_marketing_continuous_rollup IS
    'Concurrent statistical marketing rollup mart. Refresh via: REFRESH MATERIALIZED VIEW CONCURRENTLY marketing_analytics.mv_vonage_marketing_continuous_rollup;';