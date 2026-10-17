#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f analytics/.env ]; then
  set -a
  . analytics/.env
  set +a
fi
export DATA_DIR="${DATA_DIR:-./data}"
exec python -m uvicorn analytics.main:app --host 0.0.0.0 --port "${PORT:-8767}"
