"""Local HTTP contract tests; no robot or external network."""
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from upload_voice import upload, VoiceClient


class UploadTests(unittest.TestCase):
    def run_case(self, duplicate=False, fail=False):
        events = []
        class Handler(http.server.BaseHTTPRequestHandler):
            uploaded = False
            def log_message(self, *args):
                pass
            def reply(self, value):
                raw = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_GET(self):
                events.append(self.path)
                if self.path == '/settings/voice/list':
                    self.reply({'list': [{'name': 'demo', 'id': 'voice-123'}] if duplicate or Handler.uploaded else []})
                else:
                    self.reply({'taskStatus': 2, 'taskCode': 1 if fail else 0, 'taskError': ''})
            def do_POST(self):
                data = self.rfile.read(int(self.headers['Content-Length']))
                events.append((self.path, data, self.headers['Content-Type']))
                Handler.uploaded = True
                self.reply({'status': True, 'taskId': 'task-123'})
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'sample.mp3'
                path.write_bytes(b'ID3-test-bytes')
                client = VoiceClient('http://127.0.0.1:' + str(server.server_port))
                with patch('builtins.print'):
                    if duplicate:
                        with self.assertRaises(ValueError): upload(client, path, 'demo')
                    elif fail:
                        with self.assertRaises(RuntimeError): upload(client, path, 'demo')
                    else:
                        self.assertEqual(upload(client, path, 'demo')['id'], 'voice-123')
            posts = [e for e in events if isinstance(e, tuple)]
            self.assertEqual(len(posts), 0 if duplicate else 1)
            if posts:
                self.assertEqual(posts[0][0], '/upload/formdata/audio')
                for field in (b'name="name"', b'name="type"', b'name="time"', b'name="file"', b'ID3-test-bytes'):
                    self.assertIn(field, posts[0][1])
                boundary = posts[0][2].split('boundary=')[1].encode()
                self.assertTrue(posts[0][1].endswith(b'--' + boundary + b'--\r\n'))
            self.assertNotIn('/settings/voice/play', events)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
    def test_upload_and_resolve(self): self.run_case()
    def test_duplicate_blocks_post(self): self.run_case(duplicate=True)
    def test_processing_failure_no_retry(self): self.run_case(fail=True)


if __name__ == '__main__':
    unittest.main()
