#!/usr/bin/env python3
"""One-command Rover camera + YOLO + HTTP voice launcher. Existing camera/vision environments."""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

READY_MARKER = '@@ROVER_CAMERA_READY@@'


def log(message):
    print(message, flush=True)


def camera_worker(address):
    # Only this child imports the camera SDK, using the verified interpreter.
    from dobot_quad import CameraId, RobotClient
    stop = threading.Event()

    def watch_parent():
        # EOF also triggers cleanup if the launcher exits unexpectedly.
        try:
            sys.stdin.buffer.read()
        finally:
            stop.set()

    threading.Thread(target=watch_parent, daemon=True).start()
    robot = None
    opened = False
    camera = CameraId.FRONT_RGB
    try:
        log('[CAMERA] 로봇 연결 중...')
        robot = RobotClient(address)
        log('[CAMERA] 전방 카메라 스트림 시작 중...')
        uri = robot.video.open(camera)
        opened = True
        if not isinstance(uri, str) or urlparse(uri).scheme not in ('rtsp', 'rtsps'):
            raise RuntimeError(f'Camera API returned an invalid URI: {uri!r}')
        log(READY_MARKER + json.dumps({'uri': uri}))
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        if robot is not None:
            try:
                if opened:
                    log('[CAMERA] 카메라 사용 해제 중...')
                    robot.video.close(camera)
            finally:
                robot.close()
        log('[CAMERA] 종료')


def camera_environment():
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONUNBUFFERED'] = '1'
    return env


def vision_environment():
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['YOLO_OFFLINE'] = 'true'
    env['YOLO_AUTOINSTALL'] = 'false'
    env['PYTHONUNBUFFERED'] = '1'
    return env


def vision_command(args, uri, base):
    command = [args.vision_python, '-u', str(base / 'person_greet_http_v4.py'),
               '--source', uri, '--model', args.model,
               '--device', 'cpu', '--imgsz', str(args.imgsz), '--interval', str(args.interval)]
    if not args.no_show:
        command.append('--show')
    if not args.detect_only:
        command.extend(['--speak', '--voice-base-url', args.voice_base_url,
                        '--http-timeout', str(args.http_timeout)])
        if args.voice_id:
            command.extend(['--voice-id', args.voice_id])
        else:
            command.extend(['--voice-name', args.voice_name or 'greeting_original'])
    return command


def read_camera_output(stream, events):
    try:
        for line in stream:
            line = line.rstrip('\n')
            if line.startswith(READY_MARKER):
                try:
                    uri = json.loads(line[len(READY_MARKER):])['uri']
                    if not isinstance(uri, str) or urlparse(uri).scheme not in ('rtsp', 'rtsps'):
                        raise ValueError('Invalid RTSP URI')
                    events.put(('ready', uri))
                except Exception as exc:
                    events.put(('error', str(exc)))
            else:
                log(line)
    finally:
        events.put(('eof', None))


def stop_process(process, label, close_input=False):
    if process is None:
        return
    if close_input and process.stdin is not None:
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    if process.poll() is not None:
        return
    log(f'[STOP] {label} 정리 중...')
    if not close_input:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        log(f'[STOP] {label} 정상 종료 시간 초과; 종료 신호 전송')
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        log(f'[STOP] {label} 강제 종료; 카메라 원격 해제 완료는 확인되지 않음')
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def main():
    base = Path(__file__).resolve().parent
    home = Path.home()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camera-python', default=str(home / 'dobot_quad_sdk_camera/.venv_camera/bin/python'))
    p.add_argument('--vision-python', default=str(home / 'dobot_quad_sdk/.venv_vision/bin/python'))
    p.add_argument('--robot-address', default='192.168.1.6:50051')
    p.add_argument('--model', default=str(base / 'yolov8n.pt'))
    p.add_argument('--voice-base-url', default='http://192.168.1.6:22000')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--voice-name')
    group.add_argument('--voice-id')
    p.add_argument('--http-timeout', type=float, default=2.0)
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--interval', type=float, default=8.0)
    p.add_argument('--detect-only', action='store_true')
    p.add_argument('--no-show', action='store_true')
    p.add_argument('--check', action='store_true', help='Check paths only; no robot connection')
    p.add_argument('--camera-worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.camera_worker:
        camera_worker(args.robot_address)
        return 0
    if args.imgsz < 160 or args.imgsz % 32:
        p.error('imgsz must be a multiple of 32 >=160')
    if not math.isfinite(args.interval) or args.interval < 1:
        p.error('interval must be finite and >=1 second')
    for attr in ('camera_python', 'vision_python', 'model'):
        setattr(args, attr, str(Path(getattr(args, attr)).expanduser().absolute()))
    executables = [args.camera_python, args.vision_python]
    files = [base / 'person_greet_http_v4.py', Path(args.model)]
    files.append(base / 'rover_http_voice.py')
    from rover_http_voice import VoiceClient
    VoiceClient(args.voice_base_url, args.http_timeout)
    for path in executables:
        if not Path(path).is_file() or not os.access(path, os.X_OK):
            raise FileNotFoundError(f'Python executable missing: {path}')
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f'Required file missing: {path}')
    if args.check:
        log('PATH_CHECK_OK (no robot connection; module imports are checked during execution)')
        return 0
    camera = vision = None
    reader = None
    try:
        log('[1/3] 기존 카메라 환경으로 스트림 시작')
        camera = subprocess.Popen(
            [args.camera_python, '-u', str(Path(__file__).resolve()),
             '--camera-worker', '--robot-address', args.robot_address],
            cwd=str(home), env=camera_environment(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=True)
        events = queue.Queue()
        reader = threading.Thread(target=read_camera_output, args=(camera.stdout, events), daemon=True)
        reader.start()
        deadline = time.monotonic() + 45
        uri = None
        while time.monotonic() < deadline:
            try:
                kind, value = events.get(timeout=0.2)
            except queue.Empty:
                continue
            if kind == 'ready':
                uri = value
                break
            if kind in ('error', 'eof'):
                raise RuntimeError(f'Camera startup failed ({kind}): {value or "see camera log above"}')
        if uri is None:
            raise TimeoutError('Camera did not return an RTSP URI within 45 seconds')
        if camera.poll() is not None:
            raise RuntimeError('Camera keeper exited before vision launch')
        log('[2/3] 카메라 준비 완료: ' + uri)
        log('[3/3] 사람 감지 시작 / ' + ('감지만 수행' if args.detect_only else '로봇 인사 활성화'))
        vision = subprocess.Popen(vision_command(args, uri, base), cwd=str(base),
                                  env=vision_environment(), start_new_session=True)
        log('종료: Ctrl+C 또는 영상 창에서 q. 별도 카메라 유지 터미널은 필요 없습니다.')
        while True:
            code = vision.poll()
            if code is not None:
                if code != 0:
                    raise RuntimeError(f'Vision process exited with code {code}; see its error above')
                return 0
            if camera.poll() is not None:
                raise RuntimeError('Camera keeper exited; stopping vision')
            time.sleep(0.2)
    except KeyboardInterrupt:
        log('\n종료 요청을 받았습니다.')
        return 0
    finally:
        # Avoid interrupting cleanup with a repeated Ctrl+C.
        old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            stop_process(vision, '사람 감지/음성')
            stop_process(camera, '카메라', close_input=True)
            if reader is not None:
                reader.join(timeout=1)
            if camera is not None and camera.stdout is not None:
                camera.stdout.close()
        finally:
            signal.signal(signal.SIGINT, old_handler)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'LAUNCH_ERROR: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        raise SystemExit(1)
