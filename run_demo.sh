#!/usr/bin/env bash
set -e

echo "================================================================================"
echo "  VONAGE B2B MARKETING ATTRIBUTION & LINEAR OPTIMIZATION ENGINE"
echo "  Automated Linux/macOS Execution, Benchmarks & Quality Guards"
echo "================================================================================"
echo ""

echo "[1/5] Verifying Static Quality, Security and Leaks Guards..."
python scripts/validate_no_credentials.py
python scripts/validate_no_internal_leaks.py
python scripts/validate_sql_complexity.py
python scripts/validate_byte_budget.py
python scripts/validate_dockerfile_production.py

echo ""
echo "[2/5] Synthesizing Calibrated B2B Marketing Telemetry (50,000 records)..."
python src/data_generator.py --records 50000

echo ""
echo "[3/5] Executing Decoupled Optimization Engine (SciPy HiGHS)..."
python src/core_engine.py

echo ""
echo "[4/5] Running Automated Mathematical & Invariant Pytest Suite..."
python -m pytest tests/ -v

echo ""
echo "[5/5] Executing Latency SLA and Peak Heap Memory Benchmark (30 iterations)..."
python tests/benchmark.py

echo ""
echo "================================================================================"
echo "  [SUCCESS] All Stages, Invariants, Quality Guards and Benchmarks Passed!"
echo "================================================================================"