# 5 RTSP 카메라 통신 구축

## 영상 제어와 영상 데이터

카메라 구성은 두 부분으로 나뉜다. SDK는 영상 송출을 열고 세션을 유지한다. FFmpeg 또는 OpenCV는 반환된 RTSP URI에 접속해 영상 데이터를 받는다. RTSP 주소는 저장된 동영상 파일의 다운로드 링크가 아니다.

성공한 전방 URI는 `rtsp://192.168.1.6:8554/camera1`이며 ffplay에서 TCP 전송 옵션으로 재생했다. RTSP는 세션 제어 프로토콜이고 이번 수신 명령은 RTP 데이터를 TCP 연결에 실어 받도록 선택한다. SRTP는 RTP 보호 방식, SRT는 별도의 전송 방식이므로 용어를 혼용하지 않는다.

## 카메라 시작과 유지

로봇을 정지 상태에 두고 PC를 로버 Wi-Fi에 연결한다. 아래 명령은 카메라 환경만 사용하며 기존 DDS 환경을 변경하지 않는다.

~~~bash
cd "$HOME/rover-integration"
CAM_PY="$HOME/dobot_quad_sdk_camera/.venv_camera/bin/python"
env -u PYTHONPATH "$CAM_PY" tools/camera_keepalive.py \
  --address 192.168.1.6:50051
~~~

프로그램은 `CameraId.FRONT_RGB`를 열고 실제 URI를 출력한 뒤 대기한다. 카메라가 필요한 동안 이 프로세스를 유지한다. 종료할 때 `robot.video.close(camera)`와 `robot.close()`를 호출한다.

~~~python
robot = RobotClient("192.168.1.6:50051")
uri = robot.video.open(CameraId.FRONT_RGB)
print(uri)
# 사용 중에는 프로그램 유지
robot.video.close(CameraId.FRONT_RGB)
robot.close()
~~~

이 짧은 코드는 API 관계를 보여주는 발췌다. 바로 실행하면 영상 세션을 즉시 닫으므로 실제 재생에는 대기 루프가 들어간 제공 스크립트를 사용한다.

## 별도 터미널에서 표시

~~~bash
ffplay -rtsp_transport tcp \
  "rtsp://192.168.1.6:8554/camera1"
~~~

출력 URI가 다르면 SDK가 반환한 주소로 바꾼다. 영상이 보인 뒤 ffplay를 종료하고, 마지막으로 카메라 유지 프로세스를 종료한다. 녹화나 YOLO가 사용 중이라면 유지 프로세스를 먼저 종료하지 않는다.

## 이전 오류와 해결

| 증상 | 확인된 처리 |
|---|---|
| CameraId가 없음 | 기존 SDK에 새 영상 API가 없어 별도 clone과 카메라 환경 구성 |
| grpc_service_pb2 import 오류 | 패키지 빌드·설치로 생성 파일 준비 |
| grpc_tools 없음 | 카메라 전용 환경에서 SDK 의존성 설치 |
| ROS 관련 pyyaml 경고 | PYTHONPATH 제외 후 카메라 환경의 pip check 확인 |
| VLC MRL 열기 실패 | 원인 단정 없이 ffplay TCP로 실시간 표시 성공 |
| RTSP DESCRIBE 404 | SDK 카메라 시작·유지 여부와 반환 경로를 확인 |
| YOLO stream timeout | 카메라 세션을 먼저 유지한 다음 같은 URI로 재접속 |

404가 발생했다고 카메라 IP 자체가 틀렸다고 단정하지 않는다. 서비스에는 도달했으나 해당 스트림이 비활성인 경우가 있다. 이번 통합 실행기는 이 실수를 줄이기 위해 카메라 유지 자식 프로세스를 먼저 시작한다.

## 영상 저장과 가공

실시간 표시가 자동 녹화는 아니다. 저장하려면 별도 FFmpeg 명령을 실행한다. 다음은 같은 스트림을 활용하는 재현 예이며, 이전 실기에서 이 모든 저장 단계가 완료되었다는 뜻은 아니다.

~~~bash
SESSION_DIR="$HOME/rover_camera_data/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION_DIR"

ffmpeg -n -rtsp_transport tcp \
  -i "rtsp://192.168.1.6:8554/camera1" \
  -t 60 -map 0:v:0 -an -c:v copy \
  "$SESSION_DIR/front_60s.mkv"

ffprobe -v error -show_streams -show_format -of json \
  "$SESSION_DIR/front_60s.mkv" \
  > "$SESSION_DIR/metadata.json"

mkdir -p "$SESSION_DIR/frames"
ffmpeg -n -i "$SESSION_DIR/front_60s.mkv" -vf fps=2 \
  "$SESSION_DIR/frames/frame_%06d.png"
~~~

MKV나 MP4는 컨테이너이고 H.264 같은 이름은 코덱이다. `-c:v copy`는 압축 패킷을 다시 인코딩하지 않는 저장 방식이며 센서 원시 영상이라는 뜻은 아니다. 해상도·FPS·코덱은 ffprobe 결과로 기록한다.

RGB 영상만으로 픽셀 좌표를 미터 거리로 바꿀 수 없다. 사람의 거리나 로봇 목표 위치를 얻으려면 보정, 깊이 또는 별도 추정이 필요하다. DDS의 RGB·깊이 토픽과 이번 RTSP 전방 스트림은 구분한다.
