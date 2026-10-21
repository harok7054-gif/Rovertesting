# 10 출처와 버전 관리

## 프로젝트 원본

아래 파일은 본 프로젝트의 실험·구현 근거다. PCAP과 원본 녹음은 분석에 사용했으며 배포본에는 요약만 담는다.

| 자료 | 사용한 내용 |
|---|---|
| Rover_X1_Camera_Guide_KO.docx | 성공한 ffplay URI, 카메라 설치와 유지 절차 |
| e9_motor_cmd_pub.py | 슬롯 매핑, offset, PD 값, 종료 분기 분석 |
| robot_client.py 및 kill_robot.py | 과거 고수준 클라이언트와 예외 처리 |
| voice_type_20261019_130045.txt | 실제 VoiceState 동적 타입 |
| microphone.wav 및 summary.json | 16 kHz, 15초, 150개 메시지 |
| rover_audio_receiver_v1.zip | 마이크 전용 수신기 |
| voice_send_v2.py | 24 kHz PCM 송신 및 metadata 필드 |
| rover_greeting_v1.zip | 초기 인사 정책과 구현 |
| rover_greeting_v3_update.zip | 8초 반복 및 DDS 오류 처리 변화 |
| rover_greeting_http_v4_update.zip | 최신 HTTP 통합 코드와 10개 시험 |
| rover_wifi_audio_probe_20261020_160023_791970.json | 실제 무선 gRPC 상태와 동작 목록 |
| PCAPdroid_20_10월_16_45_07.pcap | 앱 업로드, 처리 완료, 등록과 재생 상태 |
| 10월 20일 실행 화면 | 비전 패키지 버전, person 이벤트, wolf 업로드 요청 |
| 10월 8일 실행 화면과 사용자 확인 | 모터 상태 수신과 gRPC 오류 경과 |

## 공개 참고자료

1. DOBOT 공식 SDK 저장소  
   https://github.com/Dobot-Team/dobot_quad_sdk
2. 공식 설치 안내  
   https://github.com/Dobot-Team/dobot_quad_sdk/blob/07400162874e28ef70b0fbd8ed29855901f27ac1/docs/docs/getting-started/installation.md
3. 고수준 API와 영상 세션  
   https://github.com/Dobot-Team/dobot_quad_sdk/blob/07400162874e28ef70b0fbd8ed29855901f27ac1/docs/docs/api/high_level.md
4. 저수준 DDS API  
   https://github.com/Dobot-Team/dobot_quad_sdk/blob/07400162874e28ef70b0fbd8ed29855901f27ac1/docs/docs/api/low_level.md
5. 고수준 Python 의존성  
   https://github.com/Dobot-Team/dobot_quad_sdk/blob/07400162874e28ef70b0fbd8ed29855901f27ac1/high_level/python/pyproject.toml
6. FFmpeg RTSP 전송 옵션  
   https://ffmpeg.org/ffmpeg-protocols.html#rtsp
7. Ultralytics 추론 인터페이스  
   https://docs.ultralytics.com/modes/predict/
8. 저수준 제어와 시뮬레이션 참고 구현  
   https://github.com/shh444/rover-lowlevel

공개 자료 확인일은 2026년 10월 20일이다. 공식 SDK commit은 새 설치 설명의 소스 기준이며 과거 사용자 PC의 commit을 대체하지 않는다.

## 배포 범위

이 패키지는 문서와 프로젝트에서 작성한 통합 스크립트를 묶는다. 공식 SDK 전체 소스, SDK deb·wheel, YOLO 가중치, 제조사 내부 유지관리 실행파일, 원본 캡처, 실제 녹음은 포함하지 않는다. 타사 구성요소는 해당 출처의 라이선스와 제공 조건을 따른다.

일반 IP와 API 경로는 재현에 필요한 실습 값으로 기재한다. 업로드와 재생 ID의 공개 증적은 예시 기호로 바꿨다. PCAP 원문에 포함될 수 있는 장치 식별자, 인증정보 및 개인 영상·음성은 공개 저장소에 추가하지 않는다.

## 신규 파일과 보존 파일

`examples/greeting_http/*.py`, `examples/audio_receiver/receiver.py`, `examples/dds_audio_send/voice_send_v2.py`는 기존 제공 파일을 보존했다. `tools/camera_keepalive.py`와 `tools/grpc_readonly_probe.py`는 문서에 나온 절차를 독립 파일로 정리한 신규 보조 코드다. 신규 보조 코드는 구문과 인터페이스를 검토했으며 실제 로봇에서 실행한 것으로 표시하지 않는다.
