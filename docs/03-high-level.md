# 4 gRPC 고수준 제어와 기본 시험

## 고수준 API의 역할

고수준 API는 로봇 주 제어기에게 현재 상태, 사용 가능한 동작, 상태 전환과 보행 등을 요청한다. 관절별 토크를 직접 보내는 DDS 제어보다 상위 계층이며, 서버의 상태 머신과 권한 및 기종별 기능 제한을 따른다.

유선에서는 `192.168.5.2:50051`, 로버 Wi-Fi에서는 `192.168.1.6:50051`를 사용했다. 두 연결을 동시에 사용하면 각 목적지의 경로를 확인한다.

~~~bash
ip route get 192.168.5.2
ip route get 192.168.1.6
nc -vz -w 3 192.168.1.6 50051
~~~

TCP 연결 성공은 서버가 요청을 허용한다는 뜻은 아니다. UNAVAILABLE, timeout, PERMISSION_DENIED를 서로 다른 계층의 오류로 기록한다.

## 읽기 요청부터 확인

SDK RobotClient의 생성자는 버전에 따라 장애물 회피 설정 요청을 보낼 수 있다. 읽기만 확인하려면 생성된 RPC stub을 직접 사용하는 `tools/grpc_readonly_probe.py`를 이용한다. 이 파일은 문서화를 위해 정리한 점검용 코드이며 실제 로봇에서 새로 실행한 결과는 아니다.

~~~bash
cd "$HOME/rover-integration"
CAM_PY="$HOME/dobot_quad_sdk_camera/.venv_camera/bin/python"
env -u PYTHONPATH "$CAM_PY" tools/grpc_readonly_probe.py \
  --address 192.168.1.6:50051
~~~

이 점검은 `GetRobotState`와 `GetAvailableMotions`만 호출하고 각각 timeout을 적용한다. 결과에는 success, 현재 상태, 속도 비율, 로봇 타입과 동작 ID를 출력한다. RPC가 반환되었다는 사실과 동작 명령이 실행되었다는 사실은 다르다.

## 실제 응답에서 확인된 내용

10월 20일 16시 00분경 한국시간의 무선 진단 JSON에서 다음이 확인되었다.

| 항목 | 응답 |
|---|---|
| 상태 조회 | success=true |
| current_state | WALK |
| current_speed_ratio | 30 |
| obstacle_avoidance_enabled | true |
| robot_type | miniQuad |
| 동작 목록 | 27개, success=true |
| 주소 | 192.168.1.6:50051 |

WALK는 응답의 상태 이름이다. 이 값 하나로 로봇이 실제 전진 중이었다고 판단하지 않는다. 동작 목록에 wave가 있다고 음성 waveform 재생 API로 해석하지 않는다. wave는 몸체 동작 이름이며 음성 전용 HTTP 서비스와는 별개다.

## SDK 기본 예제 시험 순서

| 순서 | SDK Python 파일 | 시험 목적 |
|---|---|---|
| 1 | e1_get_available_motions.py | 서버 지원 동작 확인 |
| 2 | e2_get_current_state.py | 현재 상태 확인 |
| 3 | e5_robot_state.py | 관절과 몸체 텔레메트리 확인 |
| 4 | e3_auto_state_switch.py | 준비된 현장에서 상태 전환 |
| 5 | e4_velocity_sequence.py | 제한된 공간에서 속도 시퀀스 검증 |

예제의 기본 주소가 유선이면 Wi-Fi 테스트에 맞춰 인자나 RobotClient 주소를 변경한다. 실행하기 전 `--help`와 코드의 파라미터를 확인한다. 모든 예제를 연속으로 자동 실행하면 보행 명령까지 발생하므로 조회와 동작 시험을 분리한다.

~~~python
from dobot_quad import RobotClient

robot = RobotClient("192.168.1.6:50051")
try:
    print(robot.get_current_state_name())
    state = robot.get_state()
    print(state)
    print(robot.get_motions())
finally:
    robot.close()
~~~

실제 자세·보행 시험은 먼저 기종과 서버의 동작 목록을 확인한 뒤 이미 성공한 명령을 한 개씩 재현한다. 이번 원본에는 각 보행 거리와 자세별 계측이 모두 남아 있지 않으므로 정량 성능 표를 새로 만들어 성공값처럼 기입하지 않는다.

## 권한 오류의 해석

10월 8일에는 kill_robot 실행 경로 오류와 권한 거절이 있었다. 올바른 파일 위치는 `high_level/python/examples/kill_robot.py`이며, `high_level/python/kill_robot.py`가 아니다. 올바른 파일을 찾은 뒤에도 서버가 명령을 거절할 수 있다.

현재 코드에서 생성자나 명령 실행 중 어떤 RPC가 실패했는지 traceback으로 구분한다. 장애물 회피 설정 호출을 주석 처리한 과거 클라이언트 사본이 있으나, 이것이 서버 권한을 부여하거나 kill_robot 성공을 보장하지는 않는다. 서버 권한 문제는 승인된 제조사 설정으로 해결하고 임의 재시도로 모터 명령을 진행하지 않는다.
