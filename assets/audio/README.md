# 실행용 인사말

`greeting_demo_en.mp3`는 이 저장소의 초기 실행을 위해 새로 합성한 영어 예제다.

- 내용: “Hello. I am Rover. Nice to meet you.”
- 생성: FFmpeg의 libflite, `slt` 음성
- MP3, mono, 24000 Hz, 약 3.288초
- 기존 실험의 `greeting_original.mp3`, `wolf.mp3`나 실제 사람의 녹음이 아니다.
- 로버에 자동으로 등록되지 않는다. `tools/upload_voice.py`로 업로드한 뒤 목록과 소리를 확인한다.
- 음성 합성 엔진과 목소리 데이터는 Flite의 해당 이용 조건을 따른다: https://github.com/festvox/flite

재생성 예시(FFmpeg에 flite 필터가 있는 환경):

```bash
ffmpeg -f lavfi -i "flite=text='Hello. I am Rover. Nice to meet you.':voice=slt" \
  -ar 24000 -ac 1 -codec:a libmp3lame -b:a 96k -n greeting_demo_en.mp3
```

한국어 인사말은 본인이 녹음한 MP3를 같은 업로드 도구에 전달하면 된다. 원본 마이크 녹음은 인사말 파일이 아니므로 여기 포함하지 않았다.
