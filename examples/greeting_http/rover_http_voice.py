#!/usr/bin/env python3
"""Rover HTTP voice API, based on this robot's captured app traffic. No DDS."""
import argparse
import json
import math
import threading
import time
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class VoiceClient:
    def __init__(self, base='http://192.168.1.6:22000', timeout=2.0):
        p = urlsplit(base)
        if p.scheme not in ('http', 'https') or not p.hostname or p.path not in ('', '/') or p.query or p.fragment or p.username:
            raise ValueError('Use a base URL such as http://192.168.1.6:22000')
        if not math.isfinite(timeout) or not 0 < timeout <= 10:
            raise ValueError('timeout must be >0 and <=10 seconds')
        self.base, self.timeout = base.rstrip('/'), timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        # Deliberately no automatic retry of POST: a lost response can follow a successful play.
        with self.opener.open(req, timeout=self.timeout) as res:
            raw = res.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Unexpectedly large API response')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    def items(self):
        values = self.request('/settings/voice/list').get('list')
        if not isinstance(values, list) or any(not isinstance(x, dict) for x in values):
            raise ValueError('Invalid voice list')
        return values

    def resolve(self, name=None, voice_id=None):
        items = self.items()
        matches = [x for x in items if (x.get('id') == voice_id if voice_id else x.get('name') == name)]
        if len(matches) != 1:
            available = [{'name': x.get('name'), 'id': x.get('id')} for x in items]
            raise ValueError(f'Expected exactly one match; found {len(matches)}. Use --voice-id if names repeat. Available: {json.dumps(available, ensure_ascii=False)}')
        item = matches[0]
        if not isinstance(item.get('id'), str) or not item['id']:
            raise ValueError('Missing voice ID')
        return item

    def audio(self):
        audio = self.request('/protocol/exchange').get('audio')
        if not isinstance(audio, dict) or type(audio.get('isPlay')) is not bool:
            raise ValueError('Unknown audio state: refusing to play')
        return audio

    def play(self, voice_id):
        result = self.request('/settings/voice/play', {'id': voice_id})
        if result.get('status') is not True:
            raise RuntimeError(f'Play rejected: {result}')
        return result


class VoiceJob:
    """One HTTP worker at a time; no blocking HTTP on the detection thread.

    Recheck robot state before every POST; errors skip this opportunity. Next
    opportunity uses GET first and never blindly retries an uncertain POST.
    Robot state check + play is not atomic: keep other controllers closed.
    """
    def __init__(self, client, name=None, voice_id=None, interval=8):
        self.client, self.name, self.voice_id = client, name, voice_id
        self.interval = interval
        self.thread = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.present_at = float('-inf')
        self.next_allowed = float('-inf')
        self.started = None
        self.state = 'READY'
        self.item = None

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def eligible(self, now):
        return not self.busy and now >= self.next_allowed and not self.stop.is_set()

    def presence(self, present, now):
        with self.lock:
            self.present_at = now if present else float('-inf')

    def fresh(self):
        with self.lock:
            return not self.stop.is_set() and time.monotonic() - self.present_at <= 1.0

    def start(self, now):
        if not self.eligible(now):
            return False
        self.started = now
        self.next_allowed = now + self.interval
        self.state = 'CHECKING'
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return True

    def run(self):
        try:
            if self.item is None:
                self.item = self.client.resolve(self.name, self.voice_id)
                print(f'VOICE_SELECTED name={self.item.get("name")} id={self.item["id"]}', flush=True)
            audio = self.client.audio()
            if audio['isPlay']:
                self.state = 'ROBOT_BUSY'
                print(f'VOICE_SKIP: robot already playing id={audio.get("id")}', flush=True)
                return
            if not self.fresh():
                self.state = 'STALE_SKIP'
                return
            # Enforce interval from actual POST attempts, including uncertain timeouts.
            self.next_allowed = time.monotonic() + self.interval
            self.client.play(self.item['id'])
            self.state = 'PLAY_ACCEPTED'
            print(f'VOICE_PLAY_ACCEPTED id={self.item["id"]}', flush=True)
        except Exception as exc:
            self.state = 'HTTP_ERROR'
            self.item = None
            print(f'VOICE_ERROR: {type(exc).__name__}: {exc}. Detection continues; next attempt checks state first.', flush=True)

    def poll(self, now):
        pass

    def close(self):
        self.stop.set()
        self.presence(False, time.monotonic())
        if self.thread is not None:
            self.thread.join(timeout=2 * self.client.timeout + 1)
        # Do not issue a global stop: another controller may own the current sound.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('list', 'play-once'))
    group = p.add_mutually_exclusive_group()
    group.add_argument('--voice-name')
    group.add_argument('--voice-id')
    p.add_argument('--base-url', default='http://192.168.1.6:22000')
    p.add_argument('--timeout', type=float, default=2.0)
    args = p.parse_args()
    c = VoiceClient(args.base_url, args.timeout)
    if args.action == 'list':
        print(json.dumps(c.items(), ensure_ascii=False, indent=2))
        return 0
    if not args.voice_name and not args.voice_id:
        p.error('play-once requires --voice-name or --voice-id')
    item = c.resolve(args.voice_name, args.voice_id)
    print('SELECTED:', json.dumps(item, ensure_ascii=False), flush=True)
    if c.audio()['isPlay']:
        print('SKIPPED: robot is already playing. Wait for it to finish, then run once again.')
        return 2
    c.play(item['id'])
    print('PLAY_ACCEPTED: one POST sent. Checking robot playback state...', flush=True)
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        state = c.audio()
        if state['isPlay'] and state.get('id') == item['id']:
            print('PLAYING_CONFIRMED:', json.dumps(state), flush=True)
            print('Confirm the actual sound at the robot speaker.')
            return 0
        time.sleep(0.2)
    print('PLAY_ACCEPTED_BUT_NOT_OBSERVED: no repeat sent; short clips may finish before polling. Check the speaker.')
    return 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f'VOICE_ERROR: {type(exc).__name__}: {exc}', flush=True)
        raise SystemExit(1)
