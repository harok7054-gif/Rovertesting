#!/usr/bin/env bash
# Offline host checks only; does not contact or move a robot.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1 YOLO_OFFLINE=true YOLO_AUTOINSTALL=false
for p in .venv-camera/bin/python .venv-vision/bin/python models/yolov8n.pt assets/audio/greeting_demo_en.mp3; do
  [[ -f "$p" ]] || { echo "Missing: $p. Run bash scripts/setup_ubuntu.sh first." >&2; exit 2; }
done
.venv-camera/bin/python -m pip check
.venv-vision/bin/python -m pip check
.venv-camera/bin/python -c 'from dobot_quad import CameraId, RobotClient; print("CAMERA_IMPORT_OK", CameraId.FRONT_RGB)'
.venv-vision/bin/python - <<'PY'
import cv2, numpy as np, torch
from ultralytics import YOLO
assert "FFMPEG:                      YES" in cv2.getBuildInformation() or any(
    "FFMPEG:" in line and "YES" in line for line in cv2.getBuildInformation().splitlines())
model = YOLO("models/yolov8n.pt")
assert "person" in model.names.values(), "Model must contain person class"
model.predict(np.zeros((320, 320, 3), dtype=np.uint8), device="cpu", imgsz=320, verbose=False)
print("CPU_INFERENCE_OK", torch.__version__, cv2.__version__)
PY
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels -show_entries format=duration \
  -of json assets/audio/greeting_demo_en.mp3
python3 examples/greeting_http/test_http_voice.py
python3 tools/test_upload_voice.py
echo 'HOST_CHECK_OK (robot connectivity and speaker playback are separate tests)'
