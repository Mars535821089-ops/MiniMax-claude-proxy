#!/usr/bin/env bash
# 启动代理
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec python -m proxy.main --config config.yaml "$@"
