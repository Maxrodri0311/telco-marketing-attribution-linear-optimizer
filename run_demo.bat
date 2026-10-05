@echo off
echo ================================================================================
echo   Telecom & Cloud Communications Practice B2B MARKETING ATTRIBUTION AND LINEAR OPTIMIZATION ENGINE
echo   Automated Execution, Verification, Benchmarks and Quality Guards
echo ================================================================================
echo.

echo [1/5] Verifying Static Quality, Security and Leaks Guards...
python scripts/validate_no_credentials.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Security guard failed && exit /b %ERRORLEVEL%)

python scripts/validate_no_internal_leaks.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Internal leaks guard failed && exit /b %ERRORLEVEL%)

python scripts/validate_sql_complexity.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] SQL complexity guard failed && exit /b %ERRORLEVEL%)

python scripts/validate_byte_budget.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Byte budget guard failed && exit /b %ERRORLEVEL%)

python scripts/validate_dockerfile_production.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Docker production guard failed && exit /b %ERRORLEVEL%)

echo.
echo [2/5] Synthesizing Calibrated B2B Marketing Telemetry (50,000 records)...
python src/data_generator.py --records 50000
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Data generator failed && exit /b %ERRORLEVEL%)

echo.
echo [3/5] Executing Decoupled Optimization Engine (SciPy HiGHS)...
python src/core_engine.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Core engine failed && exit /b %ERRORLEVEL%)

echo.
echo [4/5] Running Automated Mathematical and Invariant Pytest Suite...
python -m pytest tests/ -v
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Pytest suite failed && exit /b %ERRORLEVEL%)

echo.
echo [5/5] Executing Latency SLA and Peak Heap Memory Benchmark (30 iterations)...
python tests/benchmark.py
if %ERRORLEVEL% NEQ 0 (echo [ERROR] Benchmark failed && exit /b %ERRORLEVEL%)

echo.
echo ================================================================================
echo   [SUCCESS] All Stages, Invariants, Quality Guards and Benchmarks Passed!
echo ================================================================================