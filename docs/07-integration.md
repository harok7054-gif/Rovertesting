# 8 YOLO 사람 인식과 음성 통합

## 통합 구조

최신 v4는 카메라 세션 유지 프로세스와 비전 프로세스를 분리한다. 카메라 자식은 검증된 카메라 Python으로 SDK를 불러오고 반환 URI를 부모에게 전달한다. 비전 자식은 기존 비전 Python으로 YOLO를 실행한다. HTTP 음성 요청은 비전 루프를 막지 않도록 별도 worker에서 처리한다.

이 구조에서는 DDS 음성 송신기와 유선 어댑터가 자동 인사에 필요하지 않다. 단, 카메라와 HTTP 서비스 모두 로버 Wi-Fi로 접근 가능해야 한다. 저장된 음성 재생에는 등록 ID가 필요하며 모델 가중치는 PC에 준비되어 있어야 한다.

## 파일 배치

| 파일 | 역할 |
|---|---|
| run_rover_greeting_http_v4.py | 환경 선택, 카메라 시작, 비전 시작, 자식 종료 |
| person_greet_http_v4.py | 최신 프레임 수신, person 추론, 인사 조건 |
| rover_http_voice.py | 음성 목록, 정확한 ID 선택, 상태 확인, 재생 |
| test_http_voice.py | 로컬 모의 HTTP 서버 시험 |

가중치는 코드와 같은 폴더에 넣거나 `--model`로 절대경로를 지정한다. 기본 카메라 Python은 `~/dobot_quad_sdk_camera/.venv_camera/bin/python`이고 기본 비전 Python은 `~/dobot_quad_sdk/.venv_vision/bin/python`이다. 경로가 다르면 `--camera-python`과 `--vision-python`을 사용한다.

## 단계별 기본 시험

먼저 단독 음성 재생이 의도한 파일인지 확인한다. 사람이 보인다는 이벤트만으로 업로드된 파일의 정체를 확인할 수 없기 때문이다.

~~~bash
cd "$HOME/rover-integration/examples/greeting_http"
MODEL="$HOME/dobot_quad_sdk/rover_greeting_v1/yolov8n.pt"

python3 rover_http_voice.py list
python3 rover_http_voice.py play-once --voice-name greeting_original

python3 run_rover_greeting_http_v4.py \
  --model "$MODEL" --check

python3 run_rover_greeting_http_v4.py \
  --model "$MODEL" --detect-only
~~~

`--check`는 파일과 실행 경로를 확인하며 로버에 접속하지 않는다. 모든 모듈 import까지 보증하는 검사가 아니다. `--detect-only`에서 영상창과 사람 수 변화를 확인하고 인사 이벤트가 출력되는지 본다.

~~~bash
python3 run_rover_greeting_http_v4.py \
  --model "$MODEL" \
  --voice-name greeting_original \
  --interval 8
~~~

wolf를 사용할 때는 이전 업로드 이름 `greeting_pc_test` 또는 새로 지정한 `wolf_pc_test` 중 실제 목록에 있는 이름을 선택한다. 원본 파일명만 보고 이름을 추측하지 않는다.

## 인사 조건

| 조건 | 기본값과 동작 |
|---|---|
| 모델 | COCO yolov8n, person 클래스 |
| confidence | 0.6 이상 |
| 추론 크기 | 640 |
| 계산 장치 | 통합 실행기에서는 CPU |
| 첫 인사 | 약 1초 연속 person 관측 |
| 반복 간격 | 최소 8초 |
| 추론 대기 | 완료 후 0.2초 대기; 실제 5 Hz 보장은 아님 |
| 최신성 | PC 수신 후 판단까지 1초 초과 결과 제외 |
| 재생 전 상태 | audio.isPlay=true면 건너뜀 |
| 병렬 재생 작업 | 한 번에 HTTP worker 하나 |

사람이 계속 보이면 8초 간격으로 재생 기회를 확인한다. 8초보다 긴 음성이 재생 중이면 그 기회를 건너뛴다. 여러 사람이 있어도 요청은 한 번이며 사람별 추적과 개별 인사는 구현하지 않는다.

사람이 사라지면 새로운 요청을 중단한다. 이미 로버가 재생하기 시작한 파일은 강제 종료하지 않으며 끝까지 들릴 수 있다. 카메라 관측 공백을 사람이 없는 정상 영상으로 해석하지 않는다.

## 프레임 지연과 최신 데이터

수신 스레드는 최신 프레임 한 장을 교체한다. 추론이 느려도 과거 프레임이 Python 큐에 계속 쌓이는 것을 줄이기 위한 구조다. 다만 카메라 내부, 네트워크, FFmpeg 디코더의 상류 버퍼까지 제거하는 것은 아니다.

`decision_ms`는 PC에서 프레임을 받은 뒤 추론이 끝날 때까지의 시간이다. 카메라 촬영부터 로버 스피커의 음성이 시작될 때까지의 전체 지연이 아니다. 전체 지연을 주장하려면 촬영 시각, 검출 완료, POST 시각, 실제 음향 시작을 함께 측정해야 한다.

STALE_RESULT가 반복되면 아래처럼 추론 해상도를 줄여 비교할 수 있다. 정확도와 지연의 실제 변화는 별도 측정한다.

~~~bash
python3 run_rover_greeting_http_v4.py \
  --model "$MODEL" --voice-name greeting_original \
  --interval 8 --imgsz 416
~~~

## 오류와 종료

HTTP 오류가 나면 해당 기회를 건너뛰고 다음 기회에 목록과 상태를 다시 확인한다. POST 응답이 유실되면 로버에서는 이미 재생했을 수 있으므로 같은 POST를 즉시 재전송하지 않는다. 상태 확인과 재생 POST는 서버의 원자적 한 동작이 아니므로 앱과 동시에 재생 명령을 보내지 않는다.

카메라 오류는 추가 판단을 중단하고 프로그램을 종료한다. 정상 종료는 영상창 `q` 또는 `Ctrl+C`이다. 부모는 비전 프로세스를 먼저 정리하고 카메라 자식의 stdin을 닫아 세션 해제를 유도한다. 비정상 종료나 SIGKILL에서 원격 정리 완료까지 보장하지는 않는다.

## 버전별 변화

| 버전 | 핵심 동작 | 바뀐 이유 |
|---|---|---|
| v1 | 사람이 나타나면 한 번 인사, DDS 송신 | 카메라와 스피커 연결 확인 |
| v2 | 로컬 SDK 필드와 음성 송신 구성 보완 | 실제 E7 인터페이스에 맞춤 |
| v3 | 계속 보이면 8초 간격, 음성 실패 시 감지 유지 | DDS 오류로 영상 전체가 종료되는 문제 완화 |
| HTTP v4 | 로버 등록 음성 ID를 HTTP로 재생 | 유선 DDS 의존성 없이 Wi-Fi 인사 구성 |

버전별 인사 정책이 다르다. v1의 15초 cooldown 및 3초 부재 재무장 기준을 v4의 동작 설명에 섞지 않는다.

## 현장 합격 판정

| 시험 | 관찰할 결과 |
|---|---|
| 빈 장면 | person 없음, 신규 음성 요청 없음 |
| 사람 등장 | 연속 관측 후 인사 1회 |
| 계속 체류 | 최소 간격 유지, 재생 중 중첩 없음 |
| 사람 퇴장 | 신규 요청 중단 |
| 복수 인원 | 검출 수와 무관하게 기회당 1회 요청 |
| HTTP 장애 | 오류 기록, 영상·검출 유지 |
| 카메라 장애 | 오래된 판단으로 새 요청하지 않고 종료 |
| 정상 종료 | 자식 프로세스와 카메라 세션 정리 |

이 표는 반복 검증 절차다. 전체 항목을 장시간 현장에서 측정 완료한 성능 결과로 해석하지 않는다.
