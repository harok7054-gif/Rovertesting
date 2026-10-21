# 7 음성 업로드와 저장 음성 재생

## HTTP 경로를 확인한 과정

초기에는 E7의 `rt/voice/cmd`에 PCM을 발행하는 방법을 사용했다. 유선 인터페이스 이름이 사라지면 음성 DDS 참가자를 만들 수 없어 카메라와 YOLO가 정상이어도 인사가 중단됐다. 이후 앱의 파일 업로드와 재생 과정을 PCAPdroid로 캡처하여 로버의 HTTP 서비스를 확인했다.

10월 20일 16시 45분 캡처에서는 앱이 `192.168.1.6:22000`으로 MP3를 multipart 업로드하고, 비동기 작업을 조회한 뒤 음성 목록에서 등록 파일을 찾아 ID로 재생했다. 목록에는 로버 내부 저장 경로가 나타났다. 이 절차는 앱 내부 캐시의 파일을 PC가 직접 읽는 구조와 다르다.

## 키와 식별자

| 값 | 어디에서 얻는가 | 어디에 쓰는가 |
|---|---|---|
| 로컬 파일 경로 | PC 파일 | 업로드할 바이트 선택 |
| name | 업로드 시 지정 | 목록에서 사람이 구분할 이름 |
| taskId | 업로드 응답 | 업로드·처리 작업 상태 조회 |
| id | 음성 목록 | 재생 요청의 대상 |
| saveFile 및 playFile | 음성 목록 | 로봇 내부 파일 위치 정보 |
| SSH 동적 비밀번호 | 별도 유지관리 절차 | 이번 HTTP 음성 절차와 별개 |

이번 흐름에서 “키를 받는다”는 것은 음성의 재생용 ID를 확보하는 것으로 정리한다. 캡처된 업로드 폼은 `name`, `type`, `time`, `file` 네 필드였고, 별도의 SRTP 키나 업로드 인증 키 필드는 관측되지 않았다. 이것을 모든 펌웨어에서 인증이 불필요하다는 일반 규칙으로 확대하지 않는다.

## 관측된 API

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | /settings/voice/list | 이름과 재생 ID 및 파일 경로 |
| POST | /upload/formdata/audio | 음성 파일 업로드 |
| GET | /settings/voice/taskid?taskId=… | 처리 상태 |
| POST | /settings/voice/play | JSON id를 받아 재생 요청 |
| GET | /protocol/exchange | audio.isPlay와 현재 id |
| GET | /settings/voice/property | 관측값 type=1, cycleTime=1 |

이 API는 이번 장치의 앱 패킷에서 확인한 인터페이스다. 공개 gRPC SDK의 안정적 계약으로 문서화된 음성 API라고 표기하지 않는다. 펌웨어를 바꾸면 응답 구조부터 다시 확인한다.

## PC 파일을 업로드하는 재현 명령

로버 Wi-Fi에 연결하고 파일의 실제 경로를 사용한다. 아래 예에서는 `wolf.mp3`를 업로드하되 등록 이름을 `wolf_pc_test`로 명확히 정한다. 과거 화면은 파일은 wolf.mp3인데 name은 greeting_pc_test였으므로 두 이름이 달랐다.

~~~bash
AUDIO_FILE="$HOME/wolf.mp3"
test -f "$AUDIO_FILE"

curl --noproxy '*' --connect-timeout 3 --max-time 30 \
  --fail-with-body -sS \
  "http://192.168.1.6:22000/upload/formdata/audio" \
  -H 'X-Requested-With: cc.dobot.DobotRover.global' \
  --form-string 'name=wolf_pc_test' \
  --form-string 'type=audio' \
  --form-string "time=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" \
  -F "file=@$AUDIO_FILE;type=audio/mpeg" \
  -o upload_response.json

python3 -m json.tool upload_response.json
~~~

파일이 없으면 여기서 멈춘다. `curl: (26) Failed to open/read local data`는 PC 파일 읽기 오류이며 서버의 업로드 실패 응답이 아니다. 변수명 앞에 잘못 붙은 숫자나 명령 프롬프트를 함께 복사하지 않는다. `--form-string`은 이름을 문자열로 전달하고 `-F file=@…`는 파일 바이트를 보낸다.

응답 예시는 다음과 같다. 실제 값은 해당 실행에서 읽어야 한다.

~~~json
{"taskId":"<UPLOAD_TASK_ID>","status":true}
~~~

## 처리 완료와 재생 ID 확인

~~~bash
TASK_ID="$(python3 -c \
  'import json; print(json.load(open("upload_response.json"))["taskId"])')"

curl --noproxy '*' --connect-timeout 3 --max-time 8 \
  --fail-with-body -sS --get \
  --data-urlencode "taskId=$TASK_ID" \
  "http://192.168.1.6:22000/settings/voice/taskid"
~~~

캡처의 완료 응답은 아래 형태였다.

~~~json
{
  "taskStatus": 2,
  "taskCode": 0,
  "taskResult": "Task done",
  "taskError": ""
}
~~~

이는 관측된 성공 조합이다. 다른 상태 숫자의 의미는 추측하지 않는다. 대기 중이면 처리 상태를 다시 조회하며 업로드 POST 자체를 무조건 반복하지 않는다. 완료 후 목록을 확인한다.

~~~bash
cd "$HOME/rover-integration/examples/greeting_http"
python3 rover_http_voice.py list
python3 rover_http_voice.py play-once --voice-name wolf_pc_test
~~~

과거 화면에서 업로드한 wolf는 등록 이름이 `greeting_pc_test`였으므로 그 파일을 찾으려면 해당 이름을 사용한다. 같은 이름이 여러 개이면 클라이언트는 임의 선택을 거절한다. 목록에서 구분한 정확한 ID를 `--voice-id`로 전달한다.

## 실제 인사말 사례

캡처된 `greeting_original.mp3` 업로드는 taskId를 반환했고, 작업 조회에서 Task done이 확인되었다. 이후 음성 목록에 `greeting_original`이 나타났다. 같은 id로 POST를 보낸 뒤 `audio.isPlay=true`와 동일한 id가 연속 상태 응답에서 확인되었다.

재생 대상 경로는 다음과 같은 형태였다.

~~~text
/userdata/dobot/conf/project/voice/file/save_<VOICE_ID>
~~~

따라서 이 사례에서는 파일을 로버에 등록한 뒤 PC가 식별자로 재생을 요청한다. 재생할 때마다 MP3 전체를 다시 보내지 않는다. PC의 파일도 동일한 업로드 API로 전송할 수 있으며 매번 앱을 거쳐야 하는 구조는 아니다. 재부팅 후 파일 유지 여부와 삭제 정책은 별도 시험 없이 보장하지 않는다.

## 재생 성공을 구분하는 세 단계

1. `PLAY_ACCEPTED`는 재생 요청이 수락되었다는 뜻이다.
2. `PLAYING_CONFIRMED`는 상태에서 같은 ID의 재생 중 표시를 관찰했다는 뜻이다.
3. 실제 로버 스피커에서 의도한 파일 내용과 속도를 듣는 것이 청취 검증이다.

단독 시험 클라이언트는 POST를 한 번만 보내고 최대 4초간 상태를 조회한다. 짧은 음성은 조회 사이에 끝날 수 있으므로 PLAY_ACCEPTED_BUT_NOT_OBSERVED가 곧 실패를 뜻하지 않는다. 반대로 HTTP 200만으로 소리가 실제 들렸다고 결론 내리지 않는다.

wolf 업로드 화면의 마지막 play 요청은 기존 greeting_original의 ID였다. 따라서 그 화면은 wolf 재생 성공 증거가 아니다. 새 파일의 목록 ID를 조회하는 절차를 추가한 이유가 여기에 있다.

## 초기 DDS PCM 송신 경로

유선 방식의 원리를 보존하기 위해 `examples/dds_audio_send/voice_send_v2.py`를 포함했다. 이 파일은 로컬 SDK 0.23.x E7 필드를 기준으로 Header, priority, task_id, type, path, data, flag를 채운다.

~~~bash
ffmpeg -n -i "$HOME/greeting_original.mp3" \
  -vn -ac 1 -ar 24000 -c:a pcm_s16le "$HOME/greeting_24k.wav"

DDS_PY="$HOME/dobot_quad_sdk/.venv_rover/bin/python"
export CYCLONEDDS_URI="file://$HOME/dobot_quad_sdk/cyclonedds.xml"
"$DDS_PY" examples/dds_audio_send/voice_send_v2.py --check
"$DDS_PY" examples/dds_audio_send/voice_send_v2.py \
  --wav "$HOME/greeting_24k.wav"
~~~

저장소 루트에서 실행한다. 송신기는 WAV 헤더를 제외한 PCM을 4800 bytes 단위로 전송하며 이는 24 kHz mono PCM16에서 100 ms다. 기본 flag=False는 당시 E7 예제를 따른다. `--end-flag`는 선택적 해석이며 모든 펌웨어에서의 동작을 보장하지 않는다.

PUBLISH_CALLS_COMPLETED는 로컬 발행 호출 종료이지 원격 재생 완료 응답이 아니다. 최종 HTTP 방식과 DDS 방식은 오디오 형식과 전송 경로가 다르므로 혼합하지 않는다.
