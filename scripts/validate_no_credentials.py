"""
scripts/validate_no_credentials.py - Guard Universal de Seguridad y Cero Credenciales.
Audita archivos de codigo y configuracion buscando patrones de secretos o llaves hardcodeadas.
"""

import sys
import re
from pathlib import Path

CREDENTIAL_PATTERNS = [
    (r'(?i)aws[_\-]?(access[_\-]?key|secret[_\-]?key)\s*=\s*["\'][A-Z0-9]{16,}["\']', "AWS Key"),
    (r'(?i)api[_\-]?key\s*=\s*["\'][a-zA-Z0-9]{32,}["\']', "API Key"),
    (r'(?i)password\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded Password"),
    (r'(?i)ghp_[a-zA-Z0-9]{36}', "GitHub Personal Access Token"),
    (r'(?i)xox[baprs]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}', "Slack Token"),
    (r'-----BEGIN\s+PRIVATE\s+KEY-----', "RSA/SSH Private Key"),
]

EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "build", "dist"}
INCLUDED_EXTS = {".py", ".sql", ".sh", ".bat", ".yml", ".yaml", ".json", ".md", ".txt", ".ini", ".toml"}

def scan_files():
    root = Path(__file__).resolve().parent.parent
    violations = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(excluded in path.parts for excluded in EXCLUDED_DIRS):
            continue
        if path.suffix not in INCLUDED_EXTS and path.name != "Dockerfile":
            continue
        if path.name == "validate_no_credentials.py":
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            continue

        for pattern, label in CREDENTIAL_PATTERNS:
            if re.search(pattern, content):
                violations.append((path.relative_to(root), label))

    if violations:
        print("[Security Guard FAIL] Credenciales o secretos hardcodeados detectados:")
        for file_path, label in violations:
            print(f"  -> {file_path}: Patron detectado '{label}'")
        sys.exit(1)
    else:
        print("[Security Guard PASS] Cero credenciales o secretos hardcodeados en el repositorio.")
        sys.exit(0)

if __name__ == "__main__":
    scan_files()
