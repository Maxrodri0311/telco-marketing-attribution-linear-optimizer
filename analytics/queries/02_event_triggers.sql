-- ==============================================================================
-- Telecom & Cloud Communications Practice Marketing Analytics - CAC Surge & Budget Anomaly Trigger
-- Target: PostgreSQL 16 PL/pgSQL Event Triggers & Audit Trail
-- Role: Marketing Data Scientist
-- ==============================================================================

SET search_path TO marketing_analytics, public;

CREATE TABLE IF NOT EXISTS marketing_anomaly_audit_log (
    log_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    lead_id VARCHAR(64) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    observed_cost NUMERIC(12, 2) NOT NULL,
    tenure_days NUMERIC(8, 2) NOT NULL,
    hazard_rate NUMERIC(10, 5) NOT NULL,
    anomaly_reason VARCHAR(128) NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION fn_detect_marketing_cac_anomaly()
RETURNS TRIGGER AS $$
DECLARE
    v_channel_avg_cost NUMERIC(12, 2);
BEGIN
    -- Detectar si el costo del lead supera en un 300% el promedio histórico del canal
    SELECT COALESCE(AVG(total_marketing_cost_usd), 250.0)
    INTO v_channel_avg_cost
    FROM vonage_marketing_lead_telemetry
    WHERE primary_channel = NEW.primary_channel;

    IF NEW.total_marketing_cost_usd > (v_channel_avg_cost * 3.0) AND NOT NEW.is_converted THEN
        INSERT INTO marketing_anomaly_audit_log (
            lead_id,
            channel,
            observed_cost,
            tenure_days,
            hazard_rate,
            anomaly_reason
        ) VALUES (
            NEW.lead_id,
            NEW.primary_channel,
            NEW.total_marketing_cost_usd,
            NEW.tenure_days,
            NEW.hazard_rate,
            'COST_PER_LEAD_EXCEEDS_3X_CHANNEL_BASELINE_WITHOUT_CONVERSION'
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_marketing_cac_anomaly ON vonage_marketing_lead_telemetry;

CREATE TRIGGER trg_audit_marketing_cac_anomaly
AFTER INSERT ON vonage_marketing_lead_telemetry
FOR EACH ROW
EXECUTE FUNCTION fn_detect_marketing_cac_anomaly();