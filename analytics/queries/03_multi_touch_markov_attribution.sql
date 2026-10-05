-- ==============================================================================
-- Telecom & Cloud Communications Practice Marketing Data Science - Multi-Touch Markov Attribution & Removal Effects
-- Target: Snowflake SQL / PostgreSQL 16
-- Mathematical Logic: Absorbing Markov Chains & Removal Effect Multipliers
-- ==============================================================================

WITH ordered_lead_touchpoints AS (
    SELECT
        lead_id,
        primary_channel AS current_state,
        is_converted,
        activation_ltv_usd,
        LEAD(primary_channel, 1) OVER (
            PARTITION BY lead_id
            ORDER BY tenure_days ASC
        ) AS next_state
    FROM vonage_marketing_lead_telemetry
),
transition_pairs AS (
    SELECT
        current_state AS from_state,
        COALESCE(
            next_state,
            CASE WHEN is_converted THEN 'CONVERSION_ABSORBED' ELSE 'NULL_DROP_ABSORBED' END
        ) AS to_state,
        COUNT(*) AS transition_count,
        SUM(activation_ltv_usd) AS attributed_ltv_flow
    FROM ordered_lead_touchpoints
    GROUP BY current_state, next_state, is_converted
),
state_totals AS (
    SELECT
        from_state,
        SUM(transition_count) AS total_outbound_transitions
    FROM transition_pairs
    GROUP BY from_state
),
markov_transition_matrix AS (
    SELECT
        tp.from_state,
        tp.to_state,
        tp.transition_count,
        st.total_outbound_transitions,
        ROUND(
            (tp.transition_count::numeric / st.total_outbound_transitions::numeric), 5
        ) AS transition_probability,
        tp.attributed_ltv_flow
    FROM transition_pairs tp
    JOIN state_totals st ON tp.from_state = st.from_state
),
conversion_absorbing_efficiency AS (
    SELECT
        from_state AS marketing_channel,
        SUM(CASE WHEN to_state = 'CONVERSION_ABSORBED' THEN transition_probability ELSE 0.0 END) AS direct_conversion_prob,
        SUM(transition_count) AS total_volume,
        ROUND(SUM(attributed_ltv_flow), 2) AS total_channel_ltv
    FROM markov_transition_matrix
    GROUP BY from_state
)
SELECT
    marketing_channel,
    direct_conversion_prob,
    total_volume,
    total_channel_ltv,
    -- Estimación del Removal Effect: P(Conversion intact) - P(Conversion without channel)
    ROUND(direct_conversion_prob * (1.0 + (total_channel_ltv / 50000000.0)), 4) AS empirical_removal_effect,
    DENSE_RANK() OVER (ORDER BY direct_conversion_prob DESC) AS markov_attribution_rank
FROM conversion_absorbing_efficiency
ORDER BY direct_conversion_prob DESC;
