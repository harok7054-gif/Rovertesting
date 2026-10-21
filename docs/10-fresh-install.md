# 빈 PC에서 시작하기: 설치, 모델, 음성, 통합 실행

## 바로 실행 가능한가?

Clone만으로 실행되지는 않는다. 초기 배포는 기존 실습 환경과 로버에 등록된 인사말을 전제로 했다. 이 안내와 신규 스크립트는 새 PC에 필요한 환경을 저장소 내부에 구성한다. 인터넷으로 설치를 마친 뒤 로버 Wi-Fi에 연결한다.

자동 설치 기준은 **Ubuntu 22.04 LTS, x86_64, Python 3.10, CPU 추론**이다. 화면을 보려면 로컬 데스크톱 세션이 필요하다. 다른 OS·ARM·WSL·컨테이너는 자동 설치 대상으로 검증하지 않았으며, Windows에서는 Bash 명령을 그대로 실행할 수 없다. GPU는 필요하지 않다. 패키지와 모델을 받을 인터넷, sudo 권한, 로버 및 로버 Wi-Fi 연결이 필요하다. 정확한 최소 RAM과 FPS는 아직 측정하지 않았다.

## 의존성 구성

| 구분 | 설치 항목 | 파일 / 경로 |
|---|---|---|
| OS | Python venv, Git, 컴파일 도구, FFmpeg, curl, OpenGL/GLib 런타임 | `scripts/setup_ubuntu.sh`의 apt 목록 |
| 카메라 / 고수준 | 공식 DOBOT SDK와 SDK가 요구하는 gRPC·protobuf | `requirements/camera.txt`, `.venv-camera` |
| CPU 연산 | 공식 CPU wheel의 torch·torchvision | `requirements/cpu.txt` |
| 사람 인식 | Ultralytics, OpenCV, NumPy | 루트 `requirements.txt`, `.venv-vision` |
| HTTP 음성 | Python 표준 라이브러리만 사용 | `tools/upload_voice.py`, `rover_http_voice.py` |
| 마이크 수신 선택 기능 | CycloneDDS 0.10.5 | `requirements/microphone.txt`, 별도 환경 |
| 저수준 모터 선택 기능 | 제조사 deb + Python 3.10 전용 wheel, 유선 NIC 설정 | [기존 SDK 설치 안내](01-setup.md) |

HTTP 인사 통합에는 DDS, 모터 명령, `kill_robot`가 필요하지 않다. 따라서 기본 자동 설치는 카메라와 비전만 준비한다. DDS 저수준 제어까지 사용하는 경우 기존 2·3장의 deb/wheel·인터페이스 설정 및 현장 시험을 별도로 수행한다.

SDK는 `07400162874e28ef70b0fbd8ed29855901f27ac1`로 고정한다. 비전 requirements는 호환 범위이며 전체 패키지를 정확히 고정한 lockfile은 아니다. 설치가 끝나면 `environment/*.freeze.txt`와 모델 SHA-256이 기록되므로 성공한 현장 환경을 보존할 수 있다. 기존 문서에 기록한 실험 당시 버전과 신규 설치로 선택되는 버전은 다를 수 있다.

## 1. 인터넷 연결 상태에서 설치

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/harok7054-gif/Rovertesting.git "$HOME/rover-integration"
cd "$HOME/rover-integration"
bash scripts/setup_ubuntu.sh
```

이미 clone했다면 그 폴더에서 변경사항을 먼저 확인하고 `git pull --ff-only`로 갱신한다. 기존 프로젝트 폴더 위로 새 clone을 만들지 않는다.

스크립트는 `.deps/dobot_quad_sdk`에 SDK를 받고 `.venv-camera`, `.venv-vision`을 만든다. 기존 `~/dobot_quad_sdk*` 환경은 사용하지 않는다. YOLO의 COCO `yolov8n.pt`는 `models/`에 다운로드한다. 패키지 다운로드가 실패하면 오류가 발생한 단계에서 멈춘다. SDK 경로에 변경된 소스가 있으면 자동 덮어쓰기를 하지 않는다.

설치 후 또는 로버에 접속하기 전에:

```bash
bash scripts/check_environment.sh
```

이 점검은 pip 의존성 검사, 카메라 SDK import, OpenCV FFmpeg 지원, 모델의 person 클래스 및 빈 영상 CPU 추론, MP3 메타데이터, 기존 HTTP 모의 서버 시험을 수행한다. 로버에는 접속하지 않는다. 화면이 없는 서버에서 통합할 때는 실행 명령에 `--no-show`를 추가한다.

## 2. 로버 네트워크 확인

인터넷 설치가 끝나면 로버 Wi-Fi로 연결한다. 다음 주소는 기존 실습값이며 현재 장비 주소가 다르면 바꾼다.

```bash
ip route get 192.168.1.6
ping -c 3 192.168.1.6
nc -vz -w 3 192.168.1.6 50051
nc -vz -w 3 192.168.1.6 22000
```

RTSP 8554는 카메라 세션이 열린 뒤 점검한다. 포트 연결만으로 API 권한이나 카메라·스피커 동작이 검증되는 것은 아니다.

## 3. 포함된 음성을 로버에 등록

기존 실기 인사말 `greeting_original.mp3`와 `wolf.mp3`의 원본은 이번 배포 자료에 없었다. 마이크 녹음은 이 파일들과 다른 자료다. 대신 새 영어 합성 예제 `assets/audio/greeting_demo_en.mp3`를 포함했다.

내용: **Hello. I am Rover. Nice to meet you.** 약 3.288초, 24 kHz mono MP3다. 이것은 이전 실기 녹음이 아니며 로버 재생은 현장에서 확인해야 한다. PC에서는 아래 명령으로 미리 들을 수 있다.

```bash
ffplay -nodisp -autoexit assets/audio/greeting_demo_en.mp3
python3 tools/upload_voice.py \
  --file assets/audio/greeting_demo_en.mp3 --name greeting_demo_en
```

업로더는 목록에서 중복 이름을 확인하고, MP3 multipart 업로드 → taskId 처리 완료 조회 → 목록에서 재생용 id 확인까지 수행한다. 출력 `REGISTERED`는 등록 확인이며 재생 확인은 아니다. 자동으로 소리를 내거나 기존 파일을 덮어쓰지 않는다. 파일 크기 20 MiB 제한은 이 예제 도구의 제한이지 로버 펌웨어의 최대 크기 측정값이 아니다.

같은 이름이 이미 등록되어 있으면 재업로드를 중단한다. 그 경우 다음 단계로 목록과 재생을 확인한다. 업로드 도중 timeout이 발생하면 요청이 이미 처리됐을 수 있으므로 바로 반복하지 말고 목록과 출력 taskId를 먼저 확인한다. 세부 API는 [음성 업로드 문서](06-http-audio.md)를 참고한다.

## 4. 단독 재생 후 통합

```bash
python3 examples/greeting_http/rover_http_voice.py list
python3 examples/greeting_http/rover_http_voice.py play-once \
  --voice-name greeting_demo_en

# 경로만 검사
bash scripts/run_greeting.sh --check

# 영상 및 사람 인식만 확인; q 또는 Ctrl+C로 종료
bash scripts/run_greeting.sh --detect-only

# 등록된 예제 인사말 사용
bash scripts/run_greeting.sh --voice-name greeting_demo_en --interval 8
```

스피커에서 의도한 문장이 실제로 들리는지 단독 재생에서 확인한다. 저장소의 MP3 파일 경로를 YOLO 실행기에 넘기는 방식이 아니다. 먼저 로버에 업로드하고 로버 목록의 이름 또는 id를 선택한다. 등록한 MP3가 없으면 `--voice-name`만 적어도 재생되지 않는다.

IP가 다른 예:

```bash
python3 tools/upload_voice.py --file assets/audio/greeting_demo_en.mp3 \
  --name greeting_demo_en --base-url http://ROBOT_IP:22000
bash scripts/run_greeting.sh --robot-address ROBOT_IP:50051 \
  --voice-base-url http://ROBOT_IP:22000 --voice-name greeting_demo_en
```

`ROBOT_IP`는 실제 주소로 교체한다. 기존 HTTP 클라이언트의 목록·재생 명령은 `--help`에서 base URL 옵션을 확인한다.

## 한국어 / 기존 음성으로 교체

```bash
python3 tools/upload_voice.py --file /absolute/path/my_greeting_ko.mp3 \
  --name my_greeting_ko
python3 examples/greeting_http/rover_http_voice.py play-once --voice-name my_greeting_ko
bash scripts/run_greeting.sh --voice-name my_greeting_ko
```

실제 인사말 원본을 확보하면 동일 절차로 등록할 수 있다. 개인 녹음을 공개 저장소에 올리지 않아도 로컬 파일을 로버에 바로 업로드할 수 있다.

## 검증 범위와 문서 버전

이 추가본은 설치 스크립트 구문, 업로드 도구의 모의 서버 시험, 기존 HTTP 시험, 합성 MP3 디코딩·길이를 확인한 배포 보완이다. 여기서 새 Ubuntu PC 전체 설치나 실제 로버 업로드·스피커 출력을 다시 수행한 것은 아니다. `HOST_CHECK_OK` 후에도 실제 로봇의 펌웨어, Wi-Fi, 카메라, 음성 API 시험이 필요하다.

`reports/Rover_Integration_Report_KO.docx`는 2026-10-20 실습 정리본이다. 이번 신규 환경 구축 추가분은 이 문서와 루트 README에 관리한다.

공식 설치 근거: [Ultralytics](https://docs.ultralytics.com/quickstart/), [PyTorch CPU 설치](https://pytorch.org/get-started/locally/), [DOBOT SDK](https://github.com/Dobot-Team/dobot_quad_sdk).
