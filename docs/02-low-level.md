# 3 DDS 저수준 통신과 모터 시험

## DDS가 전달하는 것

DDS는 토픽을 기준으로 데이터를 발행하고 구독한다. 로봇은 센서 상태를 내보내고 PC는 해당 타입과 QoS로 구독한다. PC가 명령 토픽에 데이터를 발행하면 로봇의 해당 서비스가 이를 받는다. 같은 네트워크에서 패킷이 보이더라도 타입, Domain, QoS가 맞아야 애플리케이션이 데이터를 읽을 수 있다.

실습의 Domain은 0이었다. SDK 기본 reader는 best_effort, writer는 reliable이며 durability는 volatile이다. best_effort writer에 reliable reader를 요구하면 매칭이 성립하지 않을 수 있다. 상태 수신 실패 때 모든 QoS를 reliable로 바꾸는 방식으로 해결하지 않는다.

## 기본 수신 시험

기존 성공한 DDS 환경과 XML을 선택하고 SDK 예제가 상대경로 `config/dds_config.yaml`을 찾을 수 있도록 `low_level/python`으로 이동한다.

~~~bash
export DDS_PY="$HOME/dobot_quad_sdk/.venv_rover/bin/python"
export CYCLONEDDS_URI="file://$HOME/dobot_quad_sdk/cyclonedds.xml"
cd "$HOME/dobot_quad_sdk/low_level/python"

# 하나씩 실행하고 Ctrl+C로 종료한 뒤 다음 시험
"$DDS_PY" e4_imu_state_sub.py
"$DDS_PY" e5_motor_state_sub.py
"$DDS_PY" e6_bms_state_sub.py
~~~

| 예제 | 확인 대상 | 합격 기준 |
|---|---|---|
| E4 | IMU 상태 | 수신값이 지속 갱신되고 멈추지 않음 |
| E5 | 모터 상태 | 관절각과 온도 등 필드가 반복 수신됨 |
| E6 | 배터리 상태 | battery_level 수신; Python 예제 출력 범위 확인 |
| E1 및 E2 | DDS RGB와 깊이 | 이번 완료 목록에 깊이 수신 성공을 추가하지 않음 |
| E3 | LED 명령 | 기능 존재와 실기 성공을 구분 |

10월 8일에는 사용자에게서 세 상태값 수신이 정상이라는 확인과 관절각·온도 수신 성공이 있었다. 토픽 발견만 성공했던 초기 상태에서 실제 데이터를 받는 단계로 넘어간 결과다.

## 모터 제어의 단위와 매핑

저수준 제어는 `rt/lower/state`로 피드백을 받고 `rt/lower/cmd`로 목표를 보낸다. E9는 다리 12관절을 16개 하드웨어 슬롯에 매핑한다.

| 논리 관절 번호 | 하드웨어 슬롯 |
|---|---|
| 0, 1, 2 | 0, 1, 2 |
| 3, 4, 5 | 4, 5, 6 |
| 6, 7, 8 | 8, 9, 10 |
| 9, 10, 11 | 12, 13, 14 |

슬롯 3, 7, 11, 15를 다리 관절로 채우지 않는다. 기종과 바퀴 구성에 따라 슬롯의 의미를 확인한다. 제공된 E9는 읽을 때 하드웨어 각도에서 MOTOR_OFFSET을 빼고, 보낼 때 다시 더한다.

~~~python
ABS2HW = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]
MOTOR_OFFSET = [
    -0.05, -0.5, 1.17, 0.0,
     0.05, -0.5, 1.17, 0.0,
    -0.05,  0.5, -1.17, 0.0,
     0.05,  0.5, -1.17, 0.0,
]
~~~

q는 rad, dq는 rad/s, tau는 N·m 단위로 해석한다. PD 명령의 의미는 목표와 현재 각도 차이에 kp를 곱하고, 목표와 현재 속도 차이에 kd를 곱한 뒤 피드포워드 토크를 더하는 것이다. 모터의 전류 제한·드라이버 상태와 실제 토크 추정값은 별도 변수다.

## 주 제어기와 제어권 전환

`kill_robot`는 gRPC 고수준 경로로 실행되는 제어기 종료 명령이다. DDS 명령이 아니며 Linux의 권한 승격 명령도 아니다. 직접 모터 명령을 보낼 때 기존 주 제어기가 같은 관절을 제어하지 않도록 공식 SDK가 요구하는 단계다.

~~~bash
GRPC_PY="$HOME/dobot_quad_sdk/high_level/python/.venv_grpc/bin/python"
"$GRPC_PY" \
  "$HOME/dobot_quad_sdk/high_level/python/examples/kill_robot.py" \
  192.168.5.2:50051
~~~

실기 모터 시험 전 로봇을 지지하고 다리의 이동 범위를 비우며 독립적인 정지 수단을 준비한다. 종료 요청이 거절되거나 실제 종료 여부가 불분명하면 저수준 모터 명령을 시작하지 않는다. `sudo`로 gRPC 서버의 접근 권한 문제가 해결되지는 않는다.

제공된 과거 `kill_robot.py`는 모든 예외를 잡고 “Kill command sent”라고 출력했다. 따라서 그 문장만으로 성공을 판단할 수 없다. 10월 8일 기록의 permission 오류는 별도로 남기고, 이후 사용자의 고수준·저수준 확인 보고와 구분한다.

## E9 원본을 읽을 때 주의할 점

첨부된 E9는 최초 10회 상태를 수집하고 사인 목표를 만든다. 진폭은 0.2 rad, kp는 30, kd는 1.2이며 sleep은 0.0022초다. 이는 약 455 Hz의 요청 간격에 해당하지만 Python 처리시간과 OS 스케줄링이 더해지므로 실제 제어 주파수 측정값은 아니다.

특히 종료 분기에서 damping 명령을 만든 뒤 `publishLowerCmd`에 도달하기 전에 `exit(0)`을 호출한다. Ctrl+C를 포함한 예외 종료에서도 damping을 보장하는 finally가 없다. 초기 목표의 사인 위상도 0에서 시작하지 않는다. 따라서 이 원본을 그대로 “안전한 최종 모터 제어기”로 배포하지 않는다.

재시험 순서는 상태 수신, 제어권 전환, damping, 현재 자세 유지, 제한된 관절의 작은 상대 동작, 종료 상태 확인이다. 상대 목표를 보내기 전 현재각 수신과 시간 유효성을 확인하고, 대상 관절과 진폭을 명시한다. 최종 패키지는 모터를 자동으로 움직이는 실행기를 기본 진입점으로 두지 않는다.

## 기존 참고 저장소와의 관계

`shh444/rover-lowlevel`은 같은 DDS 경로를 MuJoCo와 공통 인터페이스로 다루는 참고 구현이다. 해당 저장소의 9월 16일 실기 주파수, 오차, 토크, Thor 결과는 그 저장소의 실험이다. 본 Rover의 측정값으로 가져오지 않는다.

저장소의 read-only preflight와 제어 가드 설계는 다음 저수준 제어 정리 때 참고할 수 있다. 이번 문서화의 범위는 현재 Rover에서 확보한 통신과 통합 시험이며 Sim-to-Real 학습 완료를 주장하지 않는다.
