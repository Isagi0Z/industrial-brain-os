#!/usr/bin/env bash
# init_infra.sh — Run the Python infrastructure init script.
# Exits 0 on success, 1 on failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Industrial Brain OS — Infrastructure Init"
echo "========================================="
echo "Running: python scripts/init_infra.py"
echo ""

cd "${REPO_ROOT}"
python scripts/init_infra.py
