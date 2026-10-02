"""
scripts/validate_sql_complexity.py - Guard Universal de Complejidad SQL Avanzado.
Garantiza que el SQL no sea meramente decorativo y contenga patrones de nivel Senior:
Window Functions, Common Table Expressions (CTEs), Particionado o Agregaciones analiticas.
"""

import sys
import re
from pathlib import Path

WINDOW_FUNCTIONS = [
    'ROW_NUMBER', 'RANK', 'DENSE_RANK', 'NTILE', 'LAG', 'LEAD',
    'FIRST_VALUE', 'LAST_VALUE', 'NTH_VALUE', 'PERCENTILE_CONT'
]
CTE_PATTERN = r'\bWITH\s+\w+\s+AS\s*\('
PARTITION_PATTERN = r'\bPARTITION\s+BY\b'
MATERIALIZED_VIEW = r'\bCREATE\s+(MATERIALIZED\s+)?VIEW\b'
TRIGGER_OR_FUNC = r'\bCREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|TRIGGER)\b'

def main():
    root = Path(__file__).resolve().parent.parent
    sql_files = list(root.rglob("*.sql"))

    if not sql_files:
        print("[SQL Complexity Guard PASS] No se encontraron archivos SQL en el repositorio.")
        sys.exit(0)

    total_sql_files = len(sql_files)
    complex_files = []

    for filepath in sql_files:
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore").upper()
        except Exception:
            continue

        has_window = any(func in content for func in WINDOW_FUNCTIONS)
        has_cte = bool(re.search(CTE_PATTERN, content))
        has_partition = bool(re.search(PARTITION_PATTERN, content))
        has_view = bool(re.search(MATERIALIZED_VIEW, content))
        has_func = bool(re.search(TRIGGER_OR_FUNC, content))

        if has_window or has_cte or has_partition or has_view or has_func:
            complex_files.append(filepath.name)

    if not complex_files:
        print(f"[SQL Complexity Guard FAIL] Se auditaron {total_sql_files} archivos SQL pero ninguno contiene patrones analiticos avanzados (Window Functions, CTEs o Particionado).")
        sys.exit(1)

    print(f"[SQL Complexity Guard PASS] Complejidad analitica avanzada verificada en {len(complex_files)}/{total_sql_files} archivos SQL (CTEs/Window Functions detectadas).")
    sys.exit(0)

if __name__ == "__main__":
    main()
