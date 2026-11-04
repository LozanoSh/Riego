#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Usa un entorno propio para no modificar el Python del sistema.
if [ ! -x .venv/bin/python ]; then
    if command -v uv >/dev/null 2>&1; then
        UV_CACHE_DIR="${TMPDIR:-/tmp}/riego-uv-cache" uv venv .venv
    else
        python3 -m venv .venv
    fi
fi
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
    UV_CACHE_DIR="${TMPDIR:-/tmp}/riego-uv-cache" uv pip install --python .venv/bin/python -r requirements.txt
else
    echo "El entorno no tiene pip. Instalá python3-venv y recreá .venv."
    exit 1
fi
exec .venv/bin/python app.py
