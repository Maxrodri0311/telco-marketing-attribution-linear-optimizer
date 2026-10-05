"""
src/data_generator.py - Calibrated Stochastic Domain Data Generator.
Physics: B2B Marketing Attribution & Survival Lifecycle Analytics for Telecom & Cloud Communications Practice CPaaS.
Vectorized columnar generation via Polars with zero toy placeholders.
"""

import os
import sys
import time
import argparse
from pathlib import Path
import numpy as np
import polars as pl


def generate_domain_dataset(
    num_records: int = 50000,
    output_path: str = "data/raw_dataset.parquet",
    seed: int = 42,
) -> pl.DataFrame:
    """
    Sintetiza telemetria estocastica de atribucion y ciclo de vida de leads B2B de Telecom & Cloud Communications Practice.
    Modela parametros de supervivencia Weibull h(t) y costos por canal publicitario.
    """
    print(f"[*] [Data Generator] Simulating {num_records:,} calibrated B2B marketing lead records for Telecom & Cloud Communications Practice...")
    start_time = time.time()
    rng = np.random.default_rng(seed)

    lead_ids = [f"vng_lead_{i:06d}" for i in range(1, num_records + 1)]

    # 1. Distribución de Segmento Empresarial (B2B Tiers)
    tiers = ["STARTUP_DEVELOPER", "MID_MARKET_GROWTH", "ENTERPRISE_STRATEGIC"]
    tier_probs = [0.50, 0.35, 0.15]
    lead_tiers = rng.choice(tiers, p=tier_probs, size=num_records)

    # 2. Distribución Geográfica (Target Regions)
    regions = ["NORTH_AMERICA", "EMEA", "APAC", "LATAM"]
    region_probs = [0.45, 0.30, 0.15, 0.10]
    lead_regions = rng.choice(regions, p=region_probs, size=num_records)

    # 3. Canales Principales de Captación B2B CPaaS
    channels = [
        "DEVREL_HACKATHONS",
        "PAID_SEARCH_CORE",
        "CONTENT_SEO_TECHNICAL",
        "TARGETED_OUTBOUND",
        "PROGRAMMATIC_DISPLAY",
        "PARTNER_ECOSYSTEM"
    ]
    channel_probs = [0.22, 0.28, 0.20, 0.12, 0.10, 0.08]
    lead_channels = rng.choice(channels, p=channel_probs, size=num_records)

    # 4. Número de toques publicitarios / interacciones técnicas (1 a 8)
    touch_counts = rng.geometric(p=0.35, size=num_records)
    touch_counts = np.clip(touch_counts, 1, 8)

    # 5. Costo unitario por canal y gasto acumulado (Spend USD)
    cost_base_map = {
        "DEVREL_HACKATHONS": 180.0,
        "PAID_SEARCH_CORE": 120.0,
        "CONTENT_SEO_TECHNICAL": 65.0,
        "TARGETED_OUTBOUND": 450.0,
        "PROGRAMMATIC_DISPLAY": 45.0,
        "PARTNER_ECOSYSTEM": 280.0
    }
    base_costs = np.array([cost_base_map[c] for c in lead_channels])
    noise_factors = rng.uniform(0.85, 1.25, size=num_records)
    total_spend = np.round(base_costs * (1.0 + 0.35 * (touch_counts - 1)) * noise_factors, 2)

    # 6. Parámetros de Supervivencia de Weibull (Shape k y Scale lambda)
    # k > 1.0 indica aceleración de fatiga o maduración temporal
    weibull_k_map = {
        "STARTUP_DEVELOPER": 1.45,
        "MID_MARKET_GROWTH": 1.85,
        "ENTERPRISE_STRATEGIC": 2.30
    }
    weibull_lambda_map = {
        "STARTUP_DEVELOPER": 21.0,    # Decisión rápida (días)
        "MID_MARKET_GROWTH": 45.0,    # Ciclo intermedio
        "ENTERPRISE_STRATEGIC": 75.0  # Comités de compras largos
    }

    base_k = np.array([weibull_k_map[t] for t in lead_tiers]) + rng.normal(0, 0.08, size=num_records)
    base_k = np.clip(base_k, 1.10, 2.70)

    base_lambda = np.array([weibull_lambda_map[t] for t in lead_tiers]) + rng.normal(0, 3.5, size=num_records)
    base_lambda = np.clip(base_lambda, 10.0, 95.0)

    # 7. Tiempo observado en el embudo (Tenure Days)
    # Generación estocástica Weibull: t = lambda * (-ln(U))^(1/k)
    uniform_u = rng.uniform(1e-4, 0.999, size=num_records)
    tenure_days = np.round(base_lambda * ((-np.log(uniform_u)) ** (1.0 / base_k)), 2)
    tenure_days = np.clip(tenure_days, 0.5, 120.0)

    # 8. Función de Tasa de Falla / Conversión Instantánea h(t)
    hazard_rate = np.round((base_k / base_lambda) * ((tenure_days / base_lambda) ** (base_k - 1)), 5)

    # 9. Probabilidad de Supervivencia S(t) = exp(-(t/lambda)^k)
    survival_prob = np.round(np.exp(-((tenure_days / base_lambda) ** base_k)), 4)

    # 10. Conversión / Activación de API en Producción (Bernoulli condicionada al hazard y toques)
    # Mayor engagement y mayor madurez en el embudo incrementan la probabilidad de conversión
    conversion_logits = -1.8 + 0.30 * touch_counts + 1.2 * hazard_rate + (1.0 - survival_prob) * 0.8
    # Ajuste por canal (DevRel y Technical Content convierten mejor a nivel de desarrollador)
    channel_boost = np.array([0.45 if c in ["DEVREL_HACKATHONS", "CONTENT_SEO_TECHNICAL"] else 0.10 for c in lead_channels])
    conversion_prob = 1.0 / (1.0 + np.exp(-(conversion_logits + channel_boost)))
    conversion_prob = np.clip(conversion_prob, 0.02, 0.85)

    is_converted = rng.random(size=num_records) < conversion_prob

    # 11. Lifetime Value (LTV) Proyectado o Realizado
    ltv_base_map = {
        "STARTUP_DEVELOPER": 3200.0,
        "MID_MARKET_GROWTH": 18500.0,
        "ENTERPRISE_STRATEGIC": 95000.0
    }
    ltv_scale = np.array([ltv_base_map[t] for t in lead_tiers])
    realized_ltv = np.where(
        is_converted,
        np.round(ltv_scale * rng.uniform(0.70, 1.60, size=num_records), 2),
        0.0
    )

    # 12. Ensamble en DataFrame de Polars de Alto Throughput
    df_polars = pl.DataFrame({
        "lead_id": lead_ids,
        "vonage_marketin_id": lead_ids,  # Compatibilidad backward
        "company_tier": lead_tiers,
        "status_category": lead_tiers,   # Compatibilidad backward
        "region": lead_regions,
        "primary_channel": lead_channels,
        "touchpoint_count": touch_counts.astype(np.int32),
        "volume_count": touch_counts.astype(np.float64),  # Compatibilidad backward
        "total_marketing_cost_usd": total_spend,
        "primary_metric": total_spend,   # Compatibilidad backward
        "weibull_shape_k": np.round(base_k, 4),
        "weibull_scale_lambda": np.round(base_lambda, 2),
        "tenure_days": tenure_days,
        "hazard_rate": hazard_rate,
        "survival_probability": survival_prob,
        "is_converted": is_converted,
        "is_active": is_converted.astype(bool),           # Compatibilidad backward
        "activation_ltv_usd": realized_ltv,
        "net_roi_usd": np.round(realized_ltv - total_spend, 2)
    })

    # Guardar en formato Parquet comprimido
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    df_polars.write_parquet(output_path, compression="zstd")

    elapsed_ms = (time.time() - start_time) * 1000.0
    conv_count = int(df_polars["is_converted"].sum())
    conv_rate = (conv_count / num_records) * 100.0
    total_rev = float(df_polars["activation_ltv_usd"].sum())
    total_cost = float(df_polars["total_marketing_cost_usd"].sum())

    print(f"[*] [Data Generator] Successfully synthesized {num_records:,} records in {elapsed_ms:.1f}ms -> {output_path}")
    print(f"    Converted Accounts: {conv_count:,} ({conv_rate:.1f}%) | Total Pipeline LTV: ${total_rev:,.2f} | Total Spend: ${total_cost:,.2f}")

    return df_polars


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrated Stochastic B2B Marketing Data Generator for Telecom & Cloud Communications Practice.")
    parser.add_argument("--records", type=int, default=50000)
    parser.add_argument("--output", type=str, default="data/raw_dataset.parquet")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    generate_domain_dataset(
        num_records=args.records,
        output_path=args.output,
        seed=args.seed,
    )