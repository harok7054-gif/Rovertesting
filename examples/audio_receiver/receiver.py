#!/usr/bin/env python3
"""Rover microphone -> PCM WAV. No command publishers are created."""
import argparse
import csv
import json
import signal
import time
import wave
from collections import Counter
from datetime import datetime
from pathlib import Path


class Recorder:
    def __init__(self, folder):
        self.folder = folder
        self.wav = wave.open(str(folder / 'microphone.wav'), 'wb')
        self.wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        self.csv_file = (folder / 'packets.csv').open('w', newline='')
        self.csv = csv.writer(self.csv_file)
        self.csv.writerow(['arrival_monotonic_s', 'robot_timestamp_ns', 'bytes',
                           'source', 'is_stop', 'angle', 'writer_handle', 'saved'])
        self.counts = Counter()
        self.total = 0
        self.writer = None
        self.first = None
        self.last = None
        self.prev_stamp = None
        self.prev_duration = None

    def accept(self, msg, now):
        info = getattr(msg, 'sample_info', None)
        if info is not None and not info.valid_data:
            return
        source = getattr(msg.source_, 'value', msg.source_)
        data = bytes(msg.data_)
        stamp = msg.header_.stamp_
        stamp_ns = int(stamp.sec_) * 1000000000 + int(stamp.nanosec_)
        handle = getattr(info, 'publication_handle', None)
        self.counts['messages'] += 1
        self.counts['source_' + str(source)] += 1
        if msg.is_stop_:
            self.counts['stop_flags'] += 1
        saved = False
        if source == 0 and data:
            if len(data) % 2:
                raise ValueError('Odd PCM byte count; refusing to silently corrupt audio')
            if self.writer is None:
                self.writer = handle
            if handle != self.writer:
                self.counts['other_writer_skipped'] += 1
            else:
                if self.prev_stamp is not None:
                    delta = (stamp_ns - self.prev_stamp) / 1e9
                    if delta <= 0:
                        self.counts['nonincreasing_timestamps'] += 1
                    elif delta > max(0.15, self.prev_duration * 1.5):
                        self.counts['timestamp_gap_warnings'] += 1
                self.wav.writeframes(data)
                self.total += len(data)
                self.counts['saved_packets'] += 1
                if self.first is None:
                    self.first = now
                self.last = now
                self.prev_stamp = stamp_ns
                self.prev_duration = len(data) / 32000
                saved = True
        self.csv.writerow([f'{now:.6f}', stamp_ns, len(data), source,
                           msg.is_stop_, msg.angle_, handle, saved])

    def close(self, reason):
        self.wav.close()
        self.csv_file.close()
        summary = dict(self.counts)
        summary.update(reason=reason, pcm_bytes=self.total, audio_seconds=self.total / 32000,
                       sample_rate=16000, channels=1, sample_width_bytes=2,
                       encoding='signed PCM little endian',
                       writer_handle=self.writer,
                       arrival_span_seconds=None if self.first is None else self.last-self.first,
                       note='Received chunks concatenated; gaps are not filled. Timestamp warnings are not packet-loss measurements.')
        (self.folder / 'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=15, help='Wall seconds after first microphone chunk; 0 until Ctrl+C')
    ap.add_argument('--domain', type=int, default=0)
    ap.add_argument('--wait', type=float, default=30, help='Discovery and first-data waiting allowance')
    ap.add_argument('--idle', type=float, default=10, help='Stop after this many seconds without microphone data')
    ap.add_argument('--out', type=Path, default=Path(__file__).resolve().parent / 'recordings')
    args = ap.parse_args()
    if args.seconds < 0 or args.wait <= 0 or args.idle <= 0:
        ap.error('seconds >= 0, wait > 0, idle > 0 required')
    from cyclonedds.domain import DomainParticipant
    from cyclonedds.builtin import BuiltinDataReader, BuiltinTopicDcpsPublication
    from cyclonedds.dynamic import get_types_for_typeid
    from cyclonedds.topic import Topic
    from cyclonedds.sub import DataReader
    from cyclonedds.qos import Qos, Policy
    from cyclonedds.util import duration
    stop = False
    def request_stop(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    args.out.mkdir(parents=True, exist_ok=True)
    folder = args.out / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir()
    print('Output:', folder, flush=True)
    participant = DomainParticipant(args.domain)
    discovery = BuiltinDataReader(participant, BuiltinTopicDcpsPublication)
    print('Discovering rt/voice/state writer...', flush=True)
    deadline = time.monotonic() + args.wait
    datatype = None
    attempted = set()
    while not stop and time.monotonic() < deadline and datatype is None:
        for ep in discovery.take(N=100):
            if not ep.sample_info.valid_data or ep.topic_name != 'rt/voice/state':
                continue
            if ep.type_id is None or str(ep.key) in attempted:
                continue
            attempted.add(str(ep.key))
            print('Writer:', ep.key, 'Type:', ep.type_name, flush=True)
            try:
                candidate, _ = get_types_for_typeid(participant, ep.type_id, duration(seconds=3))
                fields = getattr(candidate, '__annotations__', {})
                if not {'header_', 'data_', 'angle_', 'source_', 'is_stop_'}.issubset(fields):
                    print('Skipping incompatible field layout:', fields, flush=True)
                    continue
                datatype = candidate
                (folder / 'type.txt').write_text(str(ep.type_id) + '\n' + repr(fields) + '\n' + str(ep.qos))
                break
            except Exception as exc:
                print('Type lookup failed:', repr(exc), flush=True)
        time.sleep(0.02)
    if datatype is None:
        raise RuntimeError('No usable VoiceState writer found; see console above')
    topic = Topic(participant, 'rt/voice/state', datatype)
    # Same default matching policies as successful CLI; enlarge receive history only.
    reader = DataReader(participant, topic, qos=Qos(Policy.History.KeepLast(256)))
    print('Waiting for microphone. Timer starts at first microphone data.', flush=True)
    recorder = Recorder(folder)
    started = time.monotonic()
    last_report = started
    reason = 'interrupted'
    try:
        while not stop:
            now = time.monotonic()
            if recorder.first is not None and args.seconds and now-recorder.first >= args.seconds:
                reason = 'duration_complete'
                break
            for msg in reader.take(N=100):
                recorder.accept(msg, time.monotonic())
            now = time.monotonic()
            if recorder.first is None and now-started > args.wait:
                reason = 'no_microphone_data_timeout'
                break
            if recorder.last is not None and now-recorder.last > args.idle:
                reason = 'microphone_idle_timeout'
                break
            if now-last_report >= 1:
                print(f'packets={recorder.counts["saved_packets"]} audio={recorder.total/32000:.1f}s bytes={recorder.total}', flush=True)
                recorder.csv_file.flush()
                last_report = now
            time.sleep(0.01)
    except Exception:
        reason = 'error_partial_recording_saved'
        raise
    finally:
        recorder.close(reason)
        print('Saved:', folder, flush=True)
    return 0 if recorder.total else 2


if __name__ == '__main__':
    raise SystemExit(main())
