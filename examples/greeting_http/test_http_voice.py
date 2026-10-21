"""Offline tests using a local mock HTTP server; never connect to the robot."""
import contextlib
import io
import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from rover_http_voice import VoiceClient, VoiceJob, main
from person_greet_http_v4 import Gate


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, data, code=200):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        s = self.server.state
        s['gets'].append(self.path)
        if self.path == '/settings/voice/list':
            self.reply({'list': s['items']})
        elif self.path == '/protocol/exchange':
            if s.get('status_error'):
                self.reply({'error': 'temporary'}, 503)
            else:
                self.reply({'audio': s['audio']})
        else:
            self.reply({}, 404)

    def do_POST(self):
        s = self.server.state
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        s['posts'].append((self.path, data))
        s['audio'] = {'isPlay': True, 'id': data['id'], 'type': 3}
        if s.get('drop_reply'):
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.reply({'status': True})


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.s = {'items': [{'name': 'greeting_pc_test', 'id': 'wolf-file'}],
                  'audio': {'isPlay': False, 'id': ''}, 'gets': [], 'posts': []}
        self.server.state = self.s
        self.client = VoiceClient(self.base, timeout=0.5)
        self.job = VoiceJob(self.client, name='greeting_pc_test', interval=8)

    def attempt(self):
        self.job.presence(True, time.monotonic())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.job.start(time.monotonic()))
            self.job.thread.join(timeout=2)
        self.assertFalse(self.job.busy)

    def test_name_resolves_to_file_id_and_one_post(self):
        self.attempt()
        self.assertEqual(self.s['posts'], [('/settings/voice/play', {'id': 'wolf-file'})])
        self.assertEqual(self.job.state, 'PLAY_ACCEPTED')
        self.assertFalse(self.job.start(time.monotonic()))

    def test_busy_robot_skips(self):
        self.s['audio'] = {'isPlay': True, 'id': 'other'}
        self.attempt()
        self.assertEqual(self.s['posts'], [])
        self.assertEqual(self.job.state, 'ROBOT_BUSY')

    def test_missing_status_skips(self):
        self.s['audio'] = {}
        self.attempt()
        self.assertEqual(self.s['posts'], [])
        self.assertEqual(self.job.state, 'HTTP_ERROR')

    def test_network_failure_recovers_on_next_opportunity(self):
        self.s['status_error'] = True
        self.attempt()
        self.assertEqual(self.s['posts'], [])
        self.s['status_error'] = False
        self.job.next_allowed = 0
        self.attempt()
        self.assertEqual(len(self.s['posts']), 1)

    def test_lost_post_response_never_retries_blindly(self):
        self.s['drop_reply'] = True
        self.attempt()
        self.assertEqual(len(self.s['posts']), 1)
        self.job.next_allowed = 0
        self.attempt()  # GET sees playing and skips; no second POST.
        self.assertEqual(len(self.s['posts']), 1)
        self.assertEqual(self.job.state, 'ROBOT_BUSY')

    def test_duplicate_names_refused(self):
        self.s['items'].append({'name': 'greeting_pc_test', 'id': 'other'})
        self.attempt()
        self.assertEqual(self.s['posts'], [])
        self.assertEqual(self.client.resolve(voice_id='wolf-file')['id'], 'wolf-file')

    def test_person_lost_while_checking(self):
        original = self.client.audio
        def audio():
            self.job.presence(False, time.monotonic())
            return original()
        self.client.audio = audio
        self.attempt()
        self.assertEqual(self.s['posts'], [])
        self.assertEqual(self.job.state, 'STALE_SKIP')

    def test_closed_job_cannot_start(self):
        self.job.close()
        self.assertFalse(self.job.start(time.monotonic()))
        self.assertEqual(self.s['posts'], [])

    def test_cli_play_once_observes_same_id(self):
        out = io.StringIO()
        with patch('sys.argv', ['voice', 'play-once', '--voice-name', 'greeting_pc_test', '--base-url', self.base]):
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(), 0)
        self.assertIn('PLAYING_CONFIRMED', out.getvalue())
        self.assertEqual(len(self.s['posts']), 1)

    def test_8_second_gate_and_absence(self):
        gate = Gate()
        fires = [i / 10 for i in range(200) if gate.observe(True, i / 10)]
        self.assertEqual(fires, [1.0, 9.0, 17.0])
        self.assertFalse(gate.observe(False, 20.0))
        self.assertFalse(gate.observe(True, 20.1))
        # A new presence cannot bypass the global minimum interval.
        self.assertFalse(gate.observe(True, 20.9))


if __name__ == '__main__':
    unittest.main(verbosity=2)
