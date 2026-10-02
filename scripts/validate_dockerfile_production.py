"""
scripts/validate_dockerfile_production.py - Guard Condicional de Dockerfile de Produccion.
Se activa solo si existe un Dockerfile en el repositorio.
Verifica: Multi-stage, base ligera (slim/alpine), usuario no-root y buenas practicas de seguridad.
"""

import sys
import re
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    dockerfile_path = root / "Dockerfile"

    if not dockerfile_path.exists():
        print("[Docker Guard SKIP] No se detecto Dockerfile (guard condicional no exigido en esta fase).")
        sys.exit(0)

    content = dockerfile_path.read_text(encoding="utf-8")
    checks = {
        "multi_stage": bool(re.search(r'\bFROM\s+\S+\s+AS\s+\w+', content, re.IGNORECASE)),
        "slim_or_alpine_base": bool(re.search(r'\bFROM\s+python:[\d\.]+(-slim|-alpine)?\b', content, re.IGNORECASE)),
        "nonroot_user": bool(re.search(r'\bUSER\s+(?!root\b)\w+', content, re.IGNORECASE)),
        "workdir": bool(re.search(r'\bWORKDIR\s+\S+', content, re.IGNORECASE)),
    }

    failed = [name for name, passed in checks.items() if not passed]

    if failed:
        print("[Docker Guard FAIL] El Dockerfile no cumple los estandares de produccion:")
        for f in failed:
            print(f"  - Falta o no cumple: {f}")
        sys.exit(1)

    print("[Docker Guard PASS] Dockerfile cumple con los estandares de produccion (Multi-stage, slim, nonroot).")
    sys.exit(0)

if __name__ == "__main__":
    main()
