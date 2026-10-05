"""
tests/benchmark.py - Quantitative Latency & Memory Benchmark.
Evaluates high-throughput performance over 30 iterations:
  1. Ingestion & Columnar Filtering SLA (p95 < 100.0 ms)
  2. Constrained Linear Programming Solver SLA (p95 < 150.0 ms)
  3. Peak Heap Allocation Profile (Peak < 15.0 MB)
"""

import os
import sys
import time
import tempfile
import tracemalloc
from pathlib import Path
import numpy as np

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data_generator import generate_domain_dataset
from src.core_engine import (
    VonageMarketingOptimizationEngine,
    VonageAttributionExplainer,
    create_default_optimization_request,
    PolarsMarketingIngestionAdapter,
    DuckDBStorageAdapter,
    DomainAnalyticsEngine
)


def run_quantitative_benchmarks(iterations: int = 30, num_records: int = 10000):
    print(f"[*] [Benchmark] Synthesizing calibrated B2B dataset ({num_records:,} observations)...")
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        generate_domain_dataset(num_records=num_records, output_path=tmp_path, seed=42)

        adapter = PolarsMarketingIngestionAdapter()
        engine = VonageMarketingOptimizationEngine()
        request = create_default_optimization_request(total_budget=2500000.0)
        explainer = VonageAttributionExplainer()

        # Warmup pass
        leads = adapter.load_lead_profiles(tmp_path, limit=1000)
        res = engine.solve_budget_allocation(request, leads)
        _ = explainer.explain_allocations(res, request)

        # -------------------------------------------------------------
        # Phase 1: Columnar Ingestion Latency Profile
        # -------------------------------------------------------------
        ingestion_latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = adapter.load_lead_profiles(tmp_path, limit=1000)
            ingestion_latencies.append((time.perf_counter() - t0) * 1000.0)

        ingest_p50 = float(np.percentile(ingestion_latencies, 50))
        ingest_p95 = float(np.percentile(ingestion_latencies, 95))
        ingest_p99 = float(np.percentile(ingestion_latencies, 99))

        # -------------------------------------------------------------
        # Phase 2: Constrained Linear Programming Solver Latency
        # -------------------------------------------------------------
        solver_latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            r = engine.solve_budget_allocation(request, leads)
            _ = explainer.explain_allocations(r, request)
            solver_latencies.append((time.perf_counter() - t0) * 1000.0)

        solver_p50 = float(np.percentile(solver_latencies, 50))
        solver_p95 = float(np.percentile(solver_latencies, 95))
        solver_p99 = float(np.percentile(solver_latencies, 99))
        throughput_ops = 1000.0 / solver_p50 if solver_p50 > 0 else 0.0

        # -------------------------------------------------------------
        # Phase 3: Peak Heap Memory Profiling
        # -------------------------------------------------------------
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()

        leads_mem = adapter.load_lead_profiles(tmp_path, limit=1000)
        res_mem = engine.solve_budget_allocation(request, leads_mem)
        _ = explainer.explain_allocations(res_mem, request)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak / (1024.0 * 1024.0)

        # -------------------------------------------------------------
        # Report & Verification
        # -------------------------------------------------------------
        print("\n" + "=" * 74)
        print("  Telecom & Cloud Communications Practice MARKETING LINEAR OPTIMIZATION ENGINE - QUANTITATIVE BENCHMARK")
        print("=" * 74)
        print(f"  Dataset Population       : {num_records:,} historical lead observations")
        print(f"  Profiling Iterations     : {iterations} passes")
        print(f"  Batch Lead Ingestion     : 1,000 active B2B leads")
        print("-" * 74)
        print("  1. Columnar Ingestion & Parquet Parse (Polars):")
        print(f"     -> p50: {ingest_p50:.2f} ms | p95: {ingest_p95:.2f} ms | p99: {ingest_p99:.2f} ms")
        print(f"     -> Production SLA Target : p95 < 100.0 ms [{'PASS' if ingest_p95 < 100.0 else 'FAIL'}]")
        print("-" * 74)
        print("  2. Constrained Linear Programming Solver (SciPy HiGHS + XAI Shadows):")
        print(f"     -> p50: {solver_p50:.2f} ms | p95: {solver_p95:.2f} ms | p99: {solver_p99:.2f} ms")
        print(f"     -> Solver Throughput     : {throughput_ops:.1f} optimizations/sec")
        print(f"     -> Production SLA Target : p95 < 150.0 ms [{'PASS' if solver_p95 < 150.0 else 'FAIL'}]")
        print("-" * 74)
        print("  3. Memory Footprint Profile (tracemalloc):")
        print(f"     -> Peak Heap Allocation  : {peak_mb:.2f} MB [SLA < 15.0 MB: {'PASS' if peak_mb < 15.0 else 'FAIL'}]")
        print("=" * 74)

        assert ingest_p95 < 100.0, f"Ingestion latency SLA breach: {ingest_p95:.2f} ms >= 100.0 ms"
        assert solver_p95 < 150.0, f"Solver latency SLA breach: {solver_p95:.2f} ms >= 150.0 ms"
        assert peak_mb < 15.0, f"Peak memory threshold breach: {peak_mb:.2f} MB >= 15.0 MB"
        print("  [+] All quantitative SLA and memory constraints verified successfully.\n")

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    run_quantitative_benchmarks(iterations=30, num_records=10000)