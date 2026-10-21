# 2 Ubuntu와 Rover SDK 설치

## 재현 기준

실습 PC는 Ubuntu와 Python 3.10 계열이며, 기존 SDK 작업 경로는 `/home/jdman/dobot_quad_sdk`였다. DDS, 기존 gRPC, 새 카메라 SDK, YOLO의 패키지 요구사항이 달라 목적별 가상환경을 유지했다. 성공한 환경을 새 패키지로 일괄 교체하지 않는다.

| 환경 | 기존 위치 | 역할 |
|---|---|---|
| DDS SDK | `~/dobot_quad_sdk/.venv_rover` | pybind 기반 dds_middleware_python |
| 기존 gRPC | `~/dobot_quad_sdk/high_level/python/.venv_grpc` | 초기 고수준 SDK; 실제 경로를 먼저 확인 |
| 카메라 | `~/dobot_quad_sdk_camera/.venv_camera` | CameraId와 video API |
| 비전 | `~/dobot_quad_sdk/.venv_vision` | PyTorch CPU, OpenCV, Ultralytics |
| 마이크 타입 조사 | `~/rover_audio_probe/.venv_types` | CycloneDDS 0.10.5 동적 타입 수신 |

기존 gRPC 경로는 10월 8일 디렉터리 화면에서 확인한 위치다. 이후 다른 폴더에서 사용했다면 현재 성공한 Python의 `sys.executable` 결과를 사용한다. 가상환경 이름만으로 실제 패키지 설치 상태를 판단하지 않는다.

## 기본 도구 준비

빈 Ubuntu PC에서 인터넷에 연결한 상태로 준비한다. 이 문서의 설치 명령은 재현 절차이며, 과거 터미널 입력을 모두 그대로 보존한 기록은 아니다.

~~~bash
sudo apt update
sudo apt install -y git python3.10-venv python3-pip \
  build-essential cmake pkg-config ffmpeg curl \
  iproute2 iputils-ping netcat-openbsd

python3.10 --version
uname -m
ffmpeg -version
ffplay -version
ffprobe -version
~~~

실기 시험에는 B200이나 JupyterLab이 필요하지 않다. 로컬 CPU에서 카메라 수신, YOLO 추론, HTTP 호출을 수행한 구성이다. 모델 학습과 시뮬레이션은 별도 환경으로 관리한다.

## SDK 받기와 버전 기록

~~~bash
git clone https://github.com/Dobot-Team/dobot_quad_sdk.git \
  "$HOME/dobot_quad_sdk"
cd "$HOME/dobot_quad_sdk"
git rev-parse HEAD
~~~

문서 작성일에 확인한 공식 SDK commit은 `07400162874e28ef70b0fbd8ed29855901f27ac1`이다. 당시 dist에는 middleware 0.25.11, CPython 3.10용 x86_64와 aarch64 wheel이 있다. 기존 로컬 음성 송신 코드의 기준은 0.23.x 계열이다. 이 둘을 동일 버전으로 취급하지 않는다.

이미 성공한 SDK가 있으면 다시 clone하거나 checkout으로 덮어쓰지 않는다. 새 PC에서 문서의 공식 소스 기준을 고정하려면 새 clone 안에서 위 commit을 checkout하고 설치한다. 로봇 펌웨어와 신규 SDK의 조합은 별도 실기 확인 대상이다.

## DDS 미들웨어와 Python 바인딩

아래는 x86_64 Ubuntu와 현재 확인한 dist 파일을 사용하는 신규 설치 예다. ARM PC에는 arm64 deb와 aarch64 wheel을 선택한다. `cp310` wheel을 Python 3.12에 설치할 수는 없다.

~~~bash
cd "$HOME/dobot_quad_sdk"
sudo apt install -y libyaml-cpp0.7 cyclonedds-dev
sudo dpkg -i dist/dds-middleware-with-thirdparty_0.25.11_amd64.deb

python3.10 -m venv .venv_rover
./.venv_rover/bin/python -m pip install -U pip setuptools wheel
./.venv_rover/bin/python -m pip install \
  dist/dds_middleware_python-0.25.11-cp310-cp310-linux_x86_64.whl
./.venv_rover/bin/python -c \
  "import dds_middleware_python as d; print(d.__file__)"
~~~

Python 모듈 import 실패와 DDS 패킷 수신 실패는 다른 문제다. 공유 라이브러리 오류가 있으면 `dpkg -L dds-middleware-with-thirdparty`로 설치 경로를 확인한다. 공식 문서의 `CYCLONEDDS_HOME=/usr/local/`와 배포물의 실제 경로가 다를 수 있으므로 확인한 경로만 지정한다.

기존 DDS 화면에서 모듈 경로가 `~/.local/lib/python3.10/site-packages`로 나타난 기록이 있다. 이는 가상환경 밖 사용자 패키지가 보이던 구성임을 뜻한다. 새 PC에서는 환경 안에 명시적으로 설치하여 경로를 확인한다.

## 유선 네트워크 준비

로봇 유선 인터페이스를 PC에 연결하고 NetworkManager의 IPv4 수동 설정에서 미사용 주소, 예를 들어 `192.168.5.10/24`를 설정한다. 로봇 전용 유선 연결에는 일반적으로 인터넷 기본 게이트웨이를 추가할 필요가 없다. 예시 주소가 다른 장치와 충돌하지 않는지 확인한다.

~~~bash
ip -br link
ip -br address
ip route get 192.168.5.2
ping -c 3 192.168.5.2
~~~

USB Ethernet 어댑터가 바뀌면 인터페이스 이름도 달라질 수 있다. 과거의 `enx00e04c680052`를 다른 PC에 그대로 복사하지 않는다. `config/cyclonedds.example.xml`의 `REPLACE_WITH_ETHERNET_INTERFACE`를 현재 이름으로 바꿔 사용한다.

~~~bash
export CYCLONEDDS_URI="file://$HOME/dobot_quad_sdk/cyclonedds.xml"
printf '%s\n' "$CYCLONEDDS_URI"
~~~

`cyclonedds ps`는 해당 CLI가 설치된 Python 환경에서 실행한다. 참여자 발견과 실제 센서 메시지 수신은 각각 확인해야 한다. 진단용 XML에는 상세 trace 경로가 포함되어 있었으나 배포 예시에서는 임시 경로를 제거했다.

## 고수준 Python 환경

기존 환경을 사용할 때 먼저 아래를 검사한다. `pip`와 `python`을 서로 다른 환경에서 실행하지 않도록 `python -m pip` 형식을 사용한다.

~~~bash
GRPC_PY="$HOME/dobot_quad_sdk/high_level/python/.venv_grpc/bin/python"
"$GRPC_PY" -c "import sys, grpc; print(sys.executable); print(grpc.__version__)"
~~~

신규 설치라면 해당 SDK의 패키지를 가상환경에 설치한다. 최신 SDK의 pyproject는 grpcio와 grpcio-tools 1.78.0을 지정한다. 기존 고수준 환경에서 사용했던 grpcio 1.83.1과 충돌하지 않도록 새 카메라 환경을 만든 것이 이전 해결 방식이다.

~~~bash
python3.10 -m venv \
  "$HOME/dobot_quad_sdk/high_level/python/.venv_grpc"
GRPC_PY="$HOME/dobot_quad_sdk/high_level/python/.venv_grpc/bin/python"
"$GRPC_PY" -m pip install -U pip setuptools wheel
"$GRPC_PY" -m pip install "$HOME/dobot_quad_sdk/high_level/python"
~~~

## 카메라 환경 구성

~~~bash
git clone https://github.com/Dobot-Team/dobot_quad_sdk.git \
  "$HOME/dobot_quad_sdk_camera"
python3.10 -m venv "$HOME/dobot_quad_sdk_camera/.venv_camera"

CAM_PY="$HOME/dobot_quad_sdk_camera/.venv_camera/bin/python"
"$CAM_PY" -m pip install -U pip setuptools wheel
"$CAM_PY" -m pip install \
  "$HOME/dobot_quad_sdk_camera/high_level/python"

cd "$HOME"
env -u PYTHONPATH "$CAM_PY" -m pip check
env -u PYTHONPATH "$CAM_PY" -c \
  "from dobot_quad import CameraId; print(CameraId.FRONT_RGB)"
~~~

`grpc_service_pb2`와 같은 생성 파일을 수동으로 복사하여 맞추지 않는다. SDK의 pip 빌드·설치가 proto 코드를 생성하도록 한다. `env -u PYTHONPATH`는 해당 실행에서만 외부 소스 경로를 제외하며 ROS 설정 파일을 변경하지 않는다.

## 비전 환경 구성

~~~bash
python3.10 -m venv "$HOME/dobot_quad_sdk/.venv_vision"
VISION_PY="$HOME/dobot_quad_sdk/.venv_vision/bin/python"
"$VISION_PY" -m pip install -U pip
"$VISION_PY" -m pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cpu
"$VISION_PY" -m pip install ultralytics opencv-python
"$VISION_PY" -c \
  "import torch, cv2, ultralytics; print(torch.__version__, cv2.__version__, ultralytics.__version__)"
~~~

기존 화면의 설치 결과는 torch `2.14.1+cpu`, OpenCV `5.0.0`, Ultralytics `8.4.183`이었다. 이 값은 그 실행의 관측 기록이며 모든 PC에서 같은 결과가 나는 고정 설치 명령을 뜻하지 않는다. 현재 성공 환경에서는 재설치 대신 `pip freeze`를 보관한다.

`yolov8n.pt`는 인터넷이 있을 때 받아둔다. 이미 다운로드한 COCO 가중치를 사용하면 로버 Wi-Fi에 연결한 뒤 인터넷 없이 실행할 수 있다. 야구공 전용 `best.pt`처럼 person 클래스가 없는 모델은 이 시험에 사용하지 않는다.

## 재현 정보 보존

~~~bash
mkdir -p "$HOME/rover_environment"
"$VISION_PY" -m pip freeze > "$HOME/rover_environment/vision.txt"
"$CAM_PY" -m pip freeze > "$HOME/rover_environment/camera.txt"
git -C "$HOME/dobot_quad_sdk" rev-parse HEAD \
  > "$HOME/rover_environment/sdk_commit.txt"
git -C "$HOME/dobot_quad_sdk_camera" rev-parse HEAD \
  > "$HOME/rover_environment/camera_sdk_commit.txt"
~~~

각 시험 로그에는 Python 절대경로, SDK commit, 로봇 펌웨어, NIC 이름, 연결 방식과 시험 시각을 같이 남긴다.
