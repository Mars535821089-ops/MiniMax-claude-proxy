#!/usr/bin/env bash
# 开发模式（自动重载）
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec python -m proxy.main --config config.yaml --reload
