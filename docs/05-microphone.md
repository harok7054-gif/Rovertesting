# 6 마이크 음성 수신

## 성공한 수신 경로

로버 마이크 데이터는 유선 DDS의 `rt/voice/state`에서 수신했다. 센서 상태 구독에 쓰는 DDS와 같은 기술이지만, 모터와 음성은 토픽과 타입이 다르다. 모터 수신 성공만으로 VoiceState 타입 호환성을 보장하지 않는다.

초기 SDK E8에서 출력이 없던 상태를 동적 타입 조회와 실제 publisher 탐색으로 조사했다. 확인된 타입은 `dobotmh4::msg::dds_::VoiceState_`이며 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| header_ | 로봇 쪽 timestamp와 frame_id |
| data_ | octet 시퀀스의 음성 바이트 |
| angle_ | 메시지의 음원 각도 값 |
| source_ | kRobotMic, kUwbSignal, kApp 구분 |
| is_stop_ | 송신자가 제공하는 상태 플래그 |

수신기는 source_=0인 마이크 데이터만 저장하고 첫 마이크 writer에 고정한다. 다른 writer의 데이터와 섞지 않는다. `is_stop_`는 기록하며 녹음 종료 명령으로 취급하지 않는다.

## 기존 환경에서 실행

~~~bash
cd "$HOME/rover-integration"
export CYCLONEDDS_URI="file://$HOME/dobot_quad_sdk/cyclonedds.xml"

env -u PYTHONPATH -u PYTHONHOME -u LD_LIBRARY_PATH \
  -u CYCLONEDDS_HOME PYTHONNOUSERSITE=1 \
  "$HOME/rover_audio_probe/.venv_types/bin/python" \
  examples/audio_receiver/receiver.py --seconds 15
~~~

기존 타입 조사 환경은 CycloneDDS 0.10.5였다. SDK pybind 모듈 `dds_middleware_python`과 Python `cyclonedds`는 동일한 Python 패키지가 아니다. 빈 PC에서는 별도 환경에 해당 버전을 설치하고 동적 타입 API를 확인한다.

~~~bash
python3.10 -m venv "$HOME/rover_audio_probe/.venv_types"
"$HOME/rover_audio_probe/.venv_types/bin/python" -m pip install -U pip
"$HOME/rover_audio_probe/.venv_types/bin/python" \
  -m pip install "cyclonedds==0.10.5"
~~~

위 신규 설치는 재현용 절차이며 시스템 DDS 라이브러리와 wheel 가용성에 따라 빌드 준비가 필요할 수 있다. 기존 성공 환경에서는 설치를 반복하지 않는다.

수신 폴더에는 `microphone.wav`, `packets.csv`, `summary.json`, `type.txt`가 만들어진다. `--seconds 0`은 Ctrl+C까지 수신하며, 기본 idle 제한은 마이크 데이터가 10초간 없는 경우다.

## 15초 수신 결과

| 항목 | 실제 결과 |
|---|---|
| 수신 메시지 | 150 |
| source_=0 | 150 |
| 저장 패킷 | 150 |
| PCM payload | 480000 bytes |
| 표본화 주파수 | 16000 Hz |
| 채널 | mono |
| 샘플 크기 | 2 bytes, signed PCM little endian |
| WAV 재생 길이 | 15.0 s |
| 최초와 마지막 도착 차이 | 약 14.900484 s |
| 종료 사유 | duration_complete |

16000 samples/s × 1 channel × 2 bytes/sample = 32000 bytes/s이고, 480000 ÷ 32000 = 15초다. 패킷당 평균 3200 bytes는 0.1초 분량이다. 첫 패킷과 마지막 패킷의 시작 시각 차이가 14.9초인 것은 150개 패킷의 시작 간격이 149개이기 때문이다.

이 수치로 패킷 손실률 0%를 증명할 수는 없다. 수신기는 누락 구간을 무음으로 채우지 않으며 헤더 timestamp 경고도 손실률 측정과 다르다. 사용자는 15초 WAV에서 실제 음성이 정상적으로 들린다고 확인했다.

## 수신과 재생의 오디오 형식

마이크 수신은 16 kHz였지만 초기 E7 PCM 송신 코드의 기준은 24 kHz mono PCM16이었다. 입력과 출력의 샘플레이트가 같다고 가정하지 않는다. MP3를 HTTP로 업로드하는 최종 경로에서는 로봇 서비스가 파일을 처리하므로 PC에서 24 kHz WAV로 변환하는 절차가 필수로 적용되는 것은 아니다.
