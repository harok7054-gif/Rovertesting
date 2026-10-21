#!/usr/bin/env python3
"""Person detection with HTTP voice playback. Camera is managed by the v4 launcher."""
import argparse
import math
import os
import sys
import threading
import time
from pathlib import Path


class Gate:
    def __init__(self, hold=1.0, interval=8.0):
        self.hold, self.interval = hold, interval
        self.since = self.previous = None
        self.last_fire = float('-inf')

    def observe(self, present, now, can_trigger=True):
        # Long observation gaps are unknown, not evidence of an empty scene.
        if self.previous is not None and now - self.previous > 1.0:
            self.since = None
        self.previous = now
        if not present:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        if can_trigger and now - self.since >= self.hold and now - self.last_fire >= self.interval:
            self.last_fire = now
            return True
        return False

    def remaining(self, now):
        return max(0.0, self.interval - (now - self.last_fire))


class LatestCamera:
    def __init__(self, cv2, source):
        self.cv2, self.source = cv2, source
        self.lock = threading.Lock()
        self.latest = None
        self.sequence = 0
        self.error = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        cap = None
        try:
            cv2 = self.cv2
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])
            if not cap.isOpened():
                raise RuntimeError('Cannot open stream. Check the previously working RTSP URL.')
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Stream disconnected; restart after restoring camera')
                with self.lock:
                    self.sequence += 1
                    self.latest = (self.sequence, time.monotonic(), frame)
        except Exception as e:
            self.error = e
        finally:
            if cap is not None:
                cap.release()

    def get(self):
        with self.lock:
            return self.latest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default=os.environ.get('ROVER_RTSP'))
    p.add_argument('--model', default='yolov8n.pt', help='COCO pretrained weights, not a baseball-only model')
    p.add_argument('--device', default='cpu')
    p.add_argument('--conf', type=float, default=0.6)
    p.add_argument('--hz', type=float, default=5)
    p.add_argument('--show', action='store_true')
    p.add_argument('--speak', action='store_true', help='Enable real robot audio; otherwise events only')
    p.add_argument('--voice-base-url', default='http://192.168.1.6:22000')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--voice-name')
    group.add_argument('--voice-id')
    p.add_argument('--http-timeout', type=float, default=2.0)
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--interval', type=float, default=8.0, help='Minimum seconds between greeting request starts')
    args = p.parse_args()
    if not args.source or not args.source.startswith(('rtsp://', 'rtsps://')):
        p.error('Set ROVER_RTSP to the previously working camera URL')
    if not 0 < args.conf <= 1 or not 0 < args.hz <= 30:
        p.error('conf must be (0,1], hz must be (0,30]')
    if args.imgsz < 160 or args.imgsz % 32:
        p.error('imgsz must be >=160 and a multiple of 32')
    if not math.isfinite(args.interval) or args.interval < 1:
        p.error('interval must be finite and >=1 second')
    from rover_http_voice import VoiceClient, VoiceJob
    client = VoiceClient(args.voice_base_url, args.http_timeout)
    if not args.voice_name and not args.voice_id:
        args.voice_name = 'greeting_original'
    if not Path(args.model).is_file():
        raise FileNotFoundError('Local YOLO model not found: ' + args.model)
    os.environ['YOLO_OFFLINE'] = 'true'
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS', 'rtsp_transport;tcp')
    import cv2
    import numpy as np
    from ultralytics import YOLO
    model = YOLO(args.model)
    names = model.names
    names = names.items() if isinstance(names, dict) else enumerate(names)
    ids = [i for i, name in names if name == 'person']
    if len(ids) != 1:
        raise RuntimeError('Model must contain the person class. Use COCO pretrained weights.')
    person_id = ids[0]
    model.predict(np.zeros((480, 640, 3), dtype=np.uint8), imgsz=args.imgsz,
                  classes=[person_id], device=args.device, verbose=False)
    camera = LatestCamera(cv2, args.source)
    gate = Gate(interval=args.interval)
    last_seq = 0
    voice = VoiceJob(client, args.voice_name, args.voice_id, args.interval)
    next_inference = time.monotonic()
    last_status = float('-inf')
    stale_warning = float('-inf')
    camera_started = time.monotonic()
    print('RUNNING mode=' + ('ROBOT_SPEAKER' if args.speak else 'EVENTS_ONLY') + f' interval={args.interval}s', flush=True)
    try:
        while True:
            now = time.monotonic()
            voice.poll(now)
            if camera.error is not None:
                raise camera.error
            sample = camera.get()
            if sample is None and now - camera_started > 8:
                raise RuntimeError('No camera frame within 8 seconds. Restore the working camera stream first.')
            if sample is not None and now - sample[1] > 5:
                raise RuntimeError('Camera has stopped producing new frames for 5 seconds.')
            if args.show and cv2.waitKey(1) & 0xff == ord('q'):
                break
            if sample is None or sample[0] == last_seq or now < next_inference:
                time.sleep(0.01)
                continue
            seq, received, frame = sample
            last_seq = seq
            if now - received > 1:
                continue
            result = model.predict(frame, classes=[person_id], conf=args.conf,
                                   imgsz=args.imgsz, device=args.device, verbose=False)[0]
            done = time.monotonic()
            next_inference = done + 1 / args.hz
            # Reject delayed decisions; receive time is not the camera capture timestamp.
            if done - received > 1 or camera.error is not None:
                if done - stale_warning > 2:
                    print(f'STALE_RESULT age_ms={(done-received)*1000:.0f}; no greeting. Try --imgsz 416 on a slow CPU.', flush=True)
                    stale_warning = done
                voice.presence(False, done)
                continue
            count = len(result.boxes) if result.boxes is not None else 0
            voice.presence(count > 0, done)
            available = not args.speak or voice.eligible(done)
            if gate.observe(count > 0, done, can_trigger=available):
                print(f'[{time.strftime("%H:%M:%S")}] PERSON_CONFIRMED -> GREET persons={count} interval={args.interval}s', flush=True)
                if args.speak:
                    if voice.start(time.monotonic()):
                        gate.last_fire = voice.started
            state = voice.state if args.speak else 'EVENTS_ONLY'
            if done - last_status > 2:
                print(f'persons={count} voice={state} interval_remaining={gate.remaining(done):.1f}s decision_ms={(done-received)*1000:.0f}', flush=True)
                last_status = done
            if args.show:
                display = result.plot()
                cv2.putText(display, f'persons={count} {state} interval_wait={gate.remaining(done):.1f}s', (15, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow('Rover greeting - q to exit', display)
    finally:
        camera.stop.set()
        voice.close()
        camera.thread.join(timeout=6)
        if args.show:
            cv2.destroyAllWindows()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'GREETING_ERROR: {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(1)
