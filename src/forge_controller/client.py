"""Local prototype client; credentials are read from a private file, never argv."""
import argparse
import json
import os
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description='Submit a Forge prototype task')
    parser.add_argument('prompt')
    parser.add_argument('--status-tool', action='store_true')
    args = parser.parse_args()
    # This convenience client is for the single-user development setup. Remote
    # clients should receive only their own token, not the whole principal file.
    grants = json.loads(Path(os.environ['FORGE_PRINCIPALS_FILE']).read_text())
    owner = os.environ.get('FORGE_CLIENT_PRINCIPAL', 'mike')
    with httpx.Client(base_url=os.environ.get('FORGE_CONTROLLER_URL', 'http://127.0.0.1:8787'),
                      headers={'Authorization': 'Bearer ' + grants[owner]['token']},
                      timeout=10, trust_env=False) as client:
        response = client.post('/v1/tasks', json={'prompt': args.prompt, 'tools': ['get_service_status'] if args.status_tool else []})
        response.raise_for_status()
        task_id = response.json()['id']
        print('Task:', task_id)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                response = client.get('/v1/tasks/' + task_id)
                response.raise_for_status()
                task = response.json()
                if task['status'] in {'succeeded', 'failed', 'cancelled'}:
                    print(json.dumps(task, indent=2))
                    if task['status'] != 'succeeded':
                        raise SystemExit(1)
                    return
                time.sleep(.25)
            print('Client wait ended; retrieve task status using its ID.')
            raise SystemExit(1)
        except KeyboardInterrupt:
            client.post('/v1/tasks/' + task_id + '/cancel').raise_for_status()
            print('Cancellation requested.')


if __name__ == '__main__':
    main()
