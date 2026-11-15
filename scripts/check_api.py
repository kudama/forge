"""Check authenticated HTTPS readiness; optionally submit one synthetic task."""
import argparse
import json
from pathlib import Path
import ssl
import stat
import time
from urllib.parse import urlsplit

import httpx


def check(client, inference=False):
    response = client.get('/health/ready', headers={'Authorization': ''})
    if response.status_code != 401:
        raise ValueError('Unauthenticated readiness did not return 401')
    client.get('/health/ready').raise_for_status()
    result = {'unauthenticated_status': 401, 'authenticated_readiness': 200}
    if not inference:
        return result
    response = client.post('/v1/tasks', json={'agent': 'forge',
        'prompt': 'Call get_service_status and briefly identify that the result is synthetic.',
        'tools': ['get_service_status']})
    response.raise_for_status()
    task_id = response.json()['id']
    # Report the receipt immediately: a timeout must not prompt a blind resubmit.
    print(json.dumps({'submitted_task_id': task_id}), flush=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = client.get('/v1/tasks/'+task_id)
        response.raise_for_status()
        row = response.json()
        if row['status'] in {'succeeded', 'failed', 'cancelled'}:
            if row['status'] != 'succeeded':
                raise ValueError('Synthetic inference failed; inspect task '+task_id)
            return {**result, 'task_id': task_id, 'inference_status': row['status']}
        time.sleep(.5)
    raise ValueError('Wait timed out; retrieve task '+task_id+' without resubmitting')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--ca-file', type=Path, required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--inference', action='store_true')
    args = parser.parse_args()
    url = urlsplit(args.url)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
        or url.path not in {'', '/'} or url.query or url.fragment):
        parser.error('Use an HTTPS origin without credentials, query or path')
    info = args.token_file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > 4096:
        parser.error('Token file must be a private regular file (mode 600), at most 4 KiB')
    credential = json.loads(args.token_file.read_text())
    if (not isinstance(credential, dict) or set(credential) != {'token'}
        or not isinstance(credential['token'], str) or len(credential['token']) < 32):
        parser.error('Expected a token-only JSON credential')
    context = ssl.create_default_context(cafile=str(args.ca_file))
    with httpx.Client(base_url=args.url.rstrip('/'), verify=context, trust_env=False,
                      headers={'Authorization': 'Bearer '+credential['token']}, timeout=10) as client:
        print(json.dumps(check(client, args.inference)))


if __name__ == '__main__':
    main()
