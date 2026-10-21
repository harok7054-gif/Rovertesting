#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
exec python3 "$ROOT/examples/greeting_http/run_rover_greeting_http_v4.py" \
  --camera-python "$ROOT/.venv-camera/bin/python" \
  --vision-python "$ROOT/.venv-vision/bin/python" \
  --model "$ROOT/models/yolov8n.pt" "$@"
