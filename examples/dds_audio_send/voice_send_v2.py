#!/usr/bin/env python3
"""Rover WAV sender aligned with the user's local SDK 0.23.x E7 example.

24 kHz / mono / S16_LE WAV -> rt/voice/cmd. No motor commands.
The local E7 explicitly sets Header, priority, task_id and flag. Its continuous
stream uses flag=False. This sender follows that behavior by default; --end-flag
marks the final PCM chunk True, an optional finite-stream interpretation of the
example's 'stream-end flag' comment (not demonstrated by that example).
Publish completion does NOT verify remote reception or audible playback.
"""
import argparse
import importlib
import os
import sys
import time
import uuid
import wave


def read_audio(path):
    with wave.open(str(path), 'rb') as w:
        fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype())
        if fmt != (24000, 1, 2, 'NONE'):
            raise ValueError(f'Expected 24000 Hz, mono, PCM16 WAV; got {fmt}')
        frames = w.getnframes()
        duration = frames / 24000
        if not 0 < duration <= 20:
            raise ValueError('Greeting must be >0 and <=20 seconds')
        pcm = w.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError('Truncated WAV data')
        return pcm, duration


def make_header(dds):
    sec, nanosec = divmod(time.time_ns(), 1_000_000_000)
    stamp = dds.Time()
    stamp.sec(sec)
    stamp.nanosec(nanosec)
    header = dds.Header()
    header.stamp(stamp)
    header.frame_id('voice_cmd')
    return header


def make_cmd(dds, task_id, payload, finished=False):
    cmd = dds.VoiceCmd()
    cmd.header(make_header(dds))
    cmd.priority(dds.VoicePriority.kNormal)
    cmd.task_id(task_id)
    cmd.type('streaming')
    cmd.path('')
    cmd.data(list(payload))
    cmd.flag(bool(finished))
    return cmd


def check_api(dds):
    for cls, methods in {
        'PyDDSMiddleware': ('createVoiceCmdWriter', 'publishVoiceCmd'),
        'VoiceCmd': ('header', 'priority', 'task_id', 'type', 'path', 'data', 'flag'),
        'Header': ('stamp', 'frame_id'),
        'Time': ('sec', 'nanosec'),
        'VoicePriority': ('kNormal',),
    }.items():
        obj = getattr(dds, cls, None)
        for method in methods:
            if obj is None or not hasattr(obj, method):
                raise RuntimeError(f'SDK missing {cls}.{method}')
    # Exercise setters without constructing a DDS participant or sending audio.
    make_cmd(dds, 'api_check_only', b'\x00\x00')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wav')
    p.add_argument('--check', action='store_true')
    p.add_argument('--domain', type=int, default=0)
    p.add_argument('--end-flag', action='store_true',
                   help='Optional: flag=True on final chunk; default matches continuous E7')
    args = p.parse_args()
    if not args.check and not args.wav:
        p.error('--wav is required')
    if args.domain < 0:
        p.error('--domain must be nonnegative')
    dds = importlib.import_module('dds_middleware_python')
    print('Python:', sys.executable, flush=True)
    print('DDS module:', getattr(dds, '__file__', 'built-in'), flush=True)
    print('CYCLONEDDS_URI:', os.environ.get('CYCLONEDDS_URI', '(unset)'), flush=True)
    check_api(dds)
    if args.check:
        print('API_CHECK_OK: SDK metadata setters verified; no DDS participant created', flush=True)
        return
    pcm, duration = read_audio(args.wav)
    if not os.environ.get('CYCLONEDDS_URI'):
        raise RuntimeError('Set the previously working CYCLONEDDS_URI first')
    mw = dds.PyDDSMiddleware(args.domain)
    qos = {'reliability': 'reliable', 'history_kind': 'keep_last',
           'history_depth': 5, 'durability': 'volatile'}
    result = mw.createVoiceCmdWriter('rt/voice/cmd', qos)
    if result is False:
        raise RuntimeError('VoiceCmd writer creation returned False')
    task_id = 'rover_greet_' + uuid.uuid4().hex[:12]
    print(f'TASK={task_id} priority=kNormal frame_id=voice_cmd end_flag={args.end_flag}', flush=True)
    print('Waiting 2 seconds for discovery (remote matching is NOT verified)...', flush=True)
    time.sleep(2)
    chunk_size = 4800  # 100ms, matching the supplied E7 capture thread.
    count = 0
    for offset in range(0, len(pcm), chunk_size):
        chunk = pcm[offset:offset + chunk_size]
        is_last = offset + len(chunk) == len(pcm)
        cmd = make_cmd(dds, task_id, chunk, args.end_flag and is_last)
        result = mw.publishVoiceCmd(cmd)
        if result is False:
            raise RuntimeError(f'Publication returned False on chunk {count + 1}')
        count += 1
        if count == 1 or is_last:
            print(f'PUBLISH chunk={count} bytes={len(chunk)} flag={args.end_flag and is_last}', flush=True)
        time.sleep(len(chunk) / 48000)
    time.sleep(2)  # Allow asynchronous transport to drain; not an acknowledgment.
    print(f'PUBLISH_CALLS_COMPLETED chunks={count} bytes={len(pcm)} seconds={duration:.3f}', flush=True)
    print('Verify sound at ROBOT speaker. Remote reception/playback is not confirmed by this log.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted: additional sending stopped; buffered robot audio may continue.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'VOICE_ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
