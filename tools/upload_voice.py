#!/usr/bin/env python3
"""Upload an MP3 and resolve its registered voice ID; never play automatically."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples/greeting_http'))
from rover_http_voice import VoiceClient


def upload(client, path, name, wait_seconds=60):
    path = Path(path)
    if path.suffix.lower() != '.mp3' or not path.is_file():
        raise ValueError('Provide an existing MP3 file')
    if not 0 < path.stat().st_size <= 20 * 1024 * 1024:
        raise ValueError('Example uploader accepts files from 1 byte to 20 MiB')
    if not name or any(c in name for c in '\r\n'):
        raise ValueError('Provide a non-empty, single-line registered name')
    if any(x.get('name') == name for x in client.items()):
        raise ValueError('Name already exists. Use the existing ID or choose a new name; no overwrite performed.')
    boundary = 'RoverUpload' + uuid.uuid4().hex
    fields = {'name': name, 'type': 'audio', 'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode())
    parts.extend([path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
    req = urllib.request.Request(client.base + '/upload/formdata/audio', data=b''.join(parts),
        headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                 'X-Requested-With': 'cc.dobot.DobotRover.global'})
    # No POST retry: a timeout can occur after the upload was accepted.
    with client.opener.open(req, timeout=30) as res:
        result = json.loads(res.read(2_000_001))
    if result.get('status') is not True or not isinstance(result.get('taskId'), str):
        raise RuntimeError(f'Upload rejected or invalid response: {result}')
    task_id = result['taskId']
    print('UPLOAD_ACCEPTED taskId=' + task_id, flush=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        task = client.request('/settings/voice/taskid?' + urlencode({'taskId': task_id}))
        if task.get('taskError'):
            raise RuntimeError(f'Processing error: {task}')
        if task.get('taskStatus') == 2:
            if task.get('taskCode') != 0:
                raise RuntimeError(f'Processing failed: {task}')
            item = client.resolve(name=name)
            print('REGISTERED ' + json.dumps({'name': item['name'], 'id': item['id']}, ensure_ascii=False))
            return item
        time.sleep(1)
    raise TimeoutError(f'Processing not confirmed. Query taskId={task_id} and list before uploading again.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--base-url', default='http://192.168.1.6:22000')
    args = parser.parse_args()
    try:
        upload(VoiceClient(args.base_url, timeout=5), args.file, args.name)
    except Exception as exc:
        parser.exit(1, f'{type(exc).__name__}: {exc}\nNo automatic re-upload. Check voice list/task status first.\n')
