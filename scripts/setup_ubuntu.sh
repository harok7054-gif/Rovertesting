#!/usr/bin/env bash
# Fresh Ubuntu 22.04 x86_64, Python 3.10, CPU integration environment.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 22.04 || "$(uname -m)" != x86_64 ]]; then
  echo 'Automated setup targets Ubuntu 22.04 x86_64. See docs/10-fresh-install.md for other systems.' >&2
  exit 2
fi
sudo apt-get update
sudo apt-get install -y git python3.10-venv python3-pip build-essential \
  ffmpeg curl libgl1 libglib2.0-0 iproute2 iputils-ping netcat-openbsd
SDK_COMMIT=07400162874e28ef70b0fbd8ed29855901f27ac1
SDK="$ROOT/.deps/dobot_quad_sdk"
mkdir -p .deps models environment
if [[ ! -e "$SDK" ]]; then
  git clone https://github.com/Dobot-Team/dobot_quad_sdk.git "$SDK"
  git -C "$SDK" checkout --detach "$SDK_COMMIT"
fi
if [[ "$(git -C "$SDK" rev-parse HEAD)" != "$SDK_COMMIT" || -n "$(git -C "$SDK" status --porcelain --untracked-files=no)" ]]; then
  echo 'SDK checkout differs from the pinned clean source; preserve it and resolve manually.' >&2
  exit 2
fi
python3.10 -m venv .venv-camera
python3.10 -m venv .venv-vision
.venv-camera/bin/python -m pip install --upgrade pip setuptools wheel
.venv-camera/bin/python -m pip install -r requirements/camera.txt
.venv-vision/bin/python -m pip install --upgrade pip setuptools wheel
.venv-vision/bin/python -m pip install -r requirements/cpu.txt
.venv-vision/bin/python -m pip install -r requirements.txt
# Download once while internet is available; later inference uses this local file.
(
  cd models
  "$ROOT/.venv-vision/bin/python" -c 'from ultralytics import YOLO; YOLO("yolov8n.pt")'
)
bash scripts/check_environment.sh
.venv-camera/bin/python -m pip freeze > environment/camera.freeze.txt
.venv-vision/bin/python -m pip freeze > environment/vision.freeze.txt
git -C "$SDK" rev-parse HEAD > environment/sdk_commit.txt
sha256sum models/yolov8n.pt assets/audio/greeting_demo_en.mp3 > environment/assets.sha256
echo 'Setup complete. Next: upload audio, play once, detect-only, then integrated greeting.'
