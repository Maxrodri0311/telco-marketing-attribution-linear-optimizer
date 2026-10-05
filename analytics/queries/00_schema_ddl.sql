-- ==============================================================================
-- Telecom & Cloud Communications Practice Marketing Data Science - Enterprise B2B Telemetry Schema
-- Target: PostgreSQL 16 Enterprise / Snowflake Compatible
-- Role: Marketing Data Scientist
-- Architecture: Time-Series Range Partitioning & BRIN Indexing
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS marketing_analytics;
SET search_path TO marketing_analytics, public;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Master Marketing Lead Telemetry: Range-Partitioned by Event Timestamp
CREATE TABLE IF NOT EXISTS vonage_marketing_lead_telemetry (
    event_id UUID DEFAULT uuid_generate_v4(),
    lead_id VARCHAR(64) NOT NULL,
    company_tier VARCHAR(32) NOT NULL, -- STARTUP_DEVELOPER, MID_MARKET_GROWTH, ENTERPRISE_STRATEGIC
    region VARCHAR(32) NOT NULL,       -- NORTH_AMERICA, EMEA, APAC, LATAM
    primary_channel VARCHAR(64) NOT NULL, -- DEVREL_HACKATHONS, PAID_SEARCH_CORE, etc.
    touchpoint_count INT NOT NULL DEFAULT 1,
    total_marketing_cost_usd NUMERIC(12, 2) NOT NULL,
    weibull_shape_k NUMERIC(6, 4) NOT NULL,
    weibull_scale_lambda NUMERIC(6, 2) NOT NULL,
    tenure_days NUMERIC(8, 2) NOT NULL,
    hazard_rate NUMERIC(10, 5) NOT NULL,
    survival_probability NUMERIC(6, 4) NOT NULL,
    is_converted BOOLEAN NOT NULL DEFAULT FALSE,
    activation_ltv_usd NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_roi_usd NUMERIC(14, 2) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_vonage_marketing_telemetry PRIMARY KEY (event_timestamp, event_id)
) PARTITION BY RANGE (event_timestamp);

-- Time-Series Partitions (Rolling Quarterly Operational Windows)
CREATE TABLE IF NOT EXISTS vonage_marketing_telemetry_2026_q1 PARTITION OF vonage_marketing_lead_telemetry
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-04-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS vonage_marketing_telemetry_2026_q2 PARTITION OF vonage_marketing_lead_telemetry
    FOR VALUES FROM ('2026-04-01 00:00:00+00') TO ('2026-07-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS vonage_marketing_telemetry_default PARTITION OF vonage_marketing_lead_telemetry
    DEFAULT;

-- BRIN Index for 95% space reduction on append-only time series
CREATE INDEX IF NOT EXISTS idx_vonage_marketing_brin_timestamp 
    ON vonage_marketing_lead_telemetry USING BRIN (event_timestamp) 
    WITH (pages_per_range = 32);

-- Composite B-Tree index for low-latency operational lead filtering
CREATE INDEX IF NOT EXISTS idx_vonage_marketing_lead_triage 
    ON vonage_marketing_lead_telemetry (lead_id, company_tier, primary_channel, event_timestamp DESC);