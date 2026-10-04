"""Explicit local handoff journal: submit once, resume polling, require Forge review."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlparse

import httpx
from forge_controller.config import Settings
try:
    from scripts.work_orders import HandoffError, compile_task, load_json, validate_result
except ModuleNotFoundError:  # Direct script invocation.
    from work_orders import HandoffError, compile_task, load_json, validate_result

ID = re.compile(r'[0-9a-f]{32}')
STATES = {'queued', 'running', 'succeeded', 'failed', 'cancelled'}


def controller_url(value):
    url = urlparse(value)
    if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
        or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
        raise HandoffError('loopback_controller_required')
    return value.rstrip('/')


class Journal:
    """Private atomic records, serialized across CLI processes; no automatic replay."""
    def __init__(self, root):
        self.root = Path(root).absolute()
        if self.root.resolve() != self.root:
            raise HandoffError('private_canonical_journal_required')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.resolve() != self.root or self.root.stat().st_mode & 0o077:
            raise HandoffError('private_canonical_journal_required')

    @contextmanager
    def locked(self):
        fd = os.open(self.root/'.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1:
                raise HandoffError('private_journal_lock_required')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError:
            raise HandoffError('handoff_busy') from None
        finally:
            os.close(fd)

    def path(self, order_id):
        if not isinstance(order_id, str) or not ID.fullmatch(order_id):
            raise HandoffError('invalid_order_id')
        return self.root/(order_id+'.json')

    def read(self, order_id):
        path = self.path(order_id)
        if not path.exists() and not path.is_symlink():
            return None
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1:
            raise HandoffError('private_journal_record_required')
        return load_json(path, limit=262144)

    def write(self, record):
        path = self.path(record['order']['work_order_id'])
        payload = json.dumps(record, allow_nan=False).encode()
        if len(payload)>262144:
            raise HandoffError('journal_record_too_large')
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix='.pending-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def request(client, method, path, payload=None):
    with client.stream(method, path, json=payload) as response:
        chunks = bytearray()
        for chunk in response.iter_bytes():
            chunks.extend(chunk)
            if len(chunks)>131072:
                raise HandoffError('controller_response_too_large')
        if response.status_code >= 300:
            raise HandoffError('controller_http_'+str(response.status_code))
        return response.status_code, json.loads(chunks)


def summary(record):
    return {'work_order_id':record['order']['work_order_id'], 'submission':record['submission'],
            'task_id':record.get('task_id'), 'execution_status':record.get('execution', {}).get('status'),
            'review_required':True}


def submit(order, settings, owner, journal, client, endpoint, native=False):
    with journal.locked():
        existing = journal.read(order['work_order_id'])
        if existing:
            if (existing['order']!=order or existing['owner']!=owner or existing['controller']!=endpoint
                or existing.get('native',False)!=native):
                raise HandoffError('order_identity_conflict')
            if existing['submission'] == 'submitting':
                existing['submission']='submission_unknown'; journal.write(existing)
            if existing['submission'] != 'accepted':
                raise HandoffError('submission_not_retryable')
            return summary(existing)
        task = compile_task(order, settings, owner)
        record = {'version':1, 'order':order, 'owner':owner, 'controller':endpoint, 'submission':'submitting', 'native':native}
        journal.write(record)  # Must be durable BEFORE POST; an interrupted receipt is never replayed.
        try:
            code, receipt = request(client, 'POST', '/v1/work-orders' if native else '/v1/tasks', order if native else task)
            if (code != 202 or not isinstance(receipt, dict) or receipt.get('status')!='queued'
                or not isinstance(receipt.get('id'), str) or not ID.fullmatch(receipt['id'])):
                raise HandoffError('invalid_submission_receipt')
        except (httpx.HTTPError, HandoffError, ValueError):
            record['submission']='submission_unknown'; journal.write(record)
            raise HandoffError('submission_unknown_no_retry') from None
        record.update(submission='accepted', task_id=receipt['id'])
        journal.write(record)
        return summary(record)


def resume(order_id, settings, owner, journal, client, endpoint, validate=False):
    with journal.locked():
        record = journal.read(order_id)
        if not record:
            raise HandoffError('order_not_found')
        if record['owner']!=owner or record['controller']!=endpoint:
            raise HandoffError('order_identity_conflict')
        if record['submission']=='submitting':
            record['submission']='submission_unknown'; journal.write(record)
        if record['submission']!='accepted':
            raise HandoffError('submission_unknown_no_retry')
        _, execution = request(client, 'GET', '/v1/tasks/'+record['task_id'])
        if (not isinstance(execution, dict) or execution.get('id')!=record['task_id']
            or execution.get('owner')!=owner or execution.get('agent')!=record['order']['agent']
            or execution.get('status') not in STATES):
            raise HandoffError('execution_identity_mismatch')
        record['execution']=execution
        journal.write(record)
        output = summary(record)
        if validate and record.get('native',False):
            verdict = execution.get('validation')
            if (execution.get('work_order_id')!=order_id or execution['status']!='succeeded'
                or verdict != {'structure_valid':True,'source_valid':True,'review_required':True}
                or execution.get('snapshot')!=record['order']['source']):
                raise HandoffError('native_validation_failed')
            output['validation']=verdict
        elif validate:
            try:
                result=json.loads(execution['result'])
            except (KeyError, TypeError, ValueError):
                raise HandoffError('successful_json_result_required') from None
            output['validation']=validate_result(record['order'], result, execution, settings, owner)
        return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['submit', 'status', 'validate'])
    parser.add_argument('order', help='Order JSON path for submit; work-order ID otherwise')
    parser.add_argument('--principal', required=True)
    parser.add_argument('--journal', type=Path, default=Path('state/handoffs'))
    parser.add_argument('--native',action='store_true',help='Submit through the controller-enforced work-order API')
    args=parser.parse_args()
    if args.native and args.action!='submit':
        parser.error('--native is only valid with submit')
    try:
        settings=Settings.from_environment()
        endpoint=controller_url(os.environ.get('FORGE_CONTROLLER_URL', 'http://127.0.0.1:8787'))
        token=settings.principals[args.principal]['token']
        journal=Journal(args.journal)
        with httpx.Client(base_url=endpoint, headers={'Authorization':'Bearer '+token},
                          timeout=10, trust_env=False, follow_redirects=False) as client:
            if args.action=='submit':
                output=submit(load_json(args.order), settings, args.principal, journal, client, endpoint, args.native)
            else:
                output=resume(args.order, settings, args.principal, journal, client, endpoint, args.action=='validate')
        print(json.dumps(output))
    except HandoffError as exc:
        print('Handoff stopped: '+str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        print('Handoff stopped; check private configuration and controller availability', file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':
    main()
