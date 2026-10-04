import json
import os

import httpx
import pytest
pytest.importorskip('jsonschema')
from tests.test_work_orders import assignment
from scripts.handoff import Journal, controller_url, resume, submit
from scripts.work_orders import HandoffError

URL='http://127.0.0.1:8787'
TASK='a'*32


def connection(handler):
    return httpx.Client(base_url=URL, transport=httpx.MockTransport(handler))


def test_receipt_survives_restart_and_duplicate_does_not_post(assignment,tmp_path):
    _,settings,order,_,execution=assignment
    calls=[]
    def server(request):
        calls.append(request.method)
        if request.method=='POST':return httpx.Response(202,json={'id':TASK,'status':'queued'})
        return httpx.Response(200,json={**execution,'id':TASK})
    with connection(server) as client:
        journal=Journal(tmp_path/'private')
        assert submit(order,settings,'operator',journal,client,URL)['task_id']==TASK
        assert submit(order,settings,'operator',Journal(journal.root),client,URL)['task_id']==TASK
        output=resume(order['work_order_id'],settings,'operator',Journal(journal.root),client,URL,True)
    assert calls==['POST','GET']
    assert output['validation']['review_required']
    saved=journal.read(order['work_order_id'])
    assert 't'*40 not in json.dumps(saved)
    assert saved['execution']['status']=='succeeded'
    assert journal.path(order['work_order_id']).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('failure',['timeout','malformed','redirect','oversized','denied'])
def test_uncertain_submission_never_replayed(assignment,tmp_path,failure):
    _,settings,order,_,_=assignment
    calls=[]
    def server(request):
        calls.append(request.method)
        if failure=='timeout':raise httpx.ReadTimeout('lost acknowledgement')
        if failure=='malformed':return httpx.Response(202,json={'id':'bad','status':'queued'})
        if failure=='redirect':return httpx.Response(302)
        if failure=='denied':return httpx.Response(403)
        return httpx.Response(202,content=b'x'*131073)
    journal=Journal(tmp_path/'private')
    with connection(server) as client:
        with pytest.raises(HandoffError,match='submission_unknown'):submit(order,settings,'operator',journal,client,URL)
        with pytest.raises(HandoffError,match='not_retryable'):submit(order,settings,'operator',journal,client,URL)
    assert calls==['POST']
    assert journal.read(order['work_order_id'])['submission']=='submission_unknown'


def test_interrupted_submission_and_identity_conflict(assignment,tmp_path):
    _,settings,order,_,_=assignment
    journal=Journal(tmp_path/'private')
    journal.write({'version':1,'order':order,'owner':'operator','controller':URL,'submission':'submitting'})
    with connection(lambda request:pytest.fail('must not send')) as client:
        with pytest.raises(HandoffError,match='not_retryable'):submit(order,settings,'operator',journal,client,URL)
        with pytest.raises(HandoffError,match='identity_conflict'):resume(order['work_order_id'],settings,'other',journal,client,URL)
    assert journal.read(order['work_order_id'])['submission']=='submission_unknown'


def test_preflight_denial_sends_nothing(assignment,tmp_path):
    _,settings,order,_,_=assignment
    order['source']['revision']='0'*40
    journal=Journal(tmp_path/'private')
    with connection(lambda request:pytest.fail('must not send')) as client:
        with pytest.raises(HandoffError):submit(order,settings,'operator',journal,client,URL)
    assert journal.read(order['work_order_id']) is None


@pytest.mark.parametrize('field,value',[('owner','other'),('id','b'*32),('agent','implementer'),('status','unknown')])
def test_wrong_execution_not_saved(assignment,tmp_path,field,value):
    _,settings,order,_,execution=assignment
    journal=Journal(tmp_path/'private')
    journal.write({'version':1,'order':order,'owner':'operator','controller':URL,'submission':'accepted','task_id':TASK})
    execution={**execution,'id':TASK,field:value}
    with connection(lambda request:httpx.Response(200,json=execution)) as client:
        with pytest.raises(HandoffError,match='identity_mismatch'):resume(order['work_order_id'],settings,'operator',journal,client,URL)
    assert 'execution' not in journal.read(order['work_order_id'])


def test_private_paths_and_lock(assignment,tmp_path):
    journal=Journal(tmp_path/'private')
    with journal.locked():
        with pytest.raises(HandoffError,match='busy'):
            with Journal(journal.root).locked():pass
    target=tmp_path/'target';target.write_text('private')
    journal.path('a'*32).symlink_to(target)
    with pytest.raises(HandoffError):journal.read('a'*32)
    os.chmod(journal.root,0o755)
    with pytest.raises(HandoffError):Journal(journal.root)


@pytest.mark.parametrize('url',['https://example.com','http://127.0.0.1:8787/path','http://user:secret@localhost','http://localhost?secret=x'])
def test_remote_or_credential_urls_rejected(url):
    with pytest.raises(HandoffError):controller_url(url)


def test_receipt_write_failure_leaves_nonreplayable_attempt(assignment,tmp_path,monkeypatch):
    _,settings,order,_,_=assignment
    journal=Journal(tmp_path/'private')
    original=journal.write
    def write(record):
        if record['submission']=='accepted':raise OSError('disk unavailable')
        original(record)
    monkeypatch.setattr(journal,'write',write)
    with connection(lambda request:httpx.Response(202,json={'id':TASK,'status':'queued'})) as client:
        with pytest.raises(OSError):submit(order,settings,'operator',journal,client,URL)
    journal=Journal(journal.root)
    with connection(lambda request:pytest.fail('must not replay')) as client:
        with pytest.raises(HandoffError,match='not_retryable'):submit(order,settings,'operator',journal,client,URL)


def test_poll_failure_preserves_receipt_and_failed_task_requires_review(assignment,tmp_path):
    _,settings,order,_,execution=assignment
    journal=Journal(tmp_path/'private')
    journal.write({'version':1,'order':order,'owner':'operator','controller':URL,'submission':'accepted','task_id':TASK})
    def unavailable(request):raise httpx.ConnectError('offline')
    with connection(unavailable) as client:
        with pytest.raises(httpx.HTTPError):resume(order['work_order_id'],settings,'operator',journal,client,URL)
    assert journal.read(order['work_order_id'])['task_id']==TASK
    execution={**execution,'id':TASK,'status':'failed','result':None}
    with connection(lambda request:httpx.Response(200,json=execution)) as client:
        assert resume(order['work_order_id'],settings,'operator',journal,client,URL)['execution_status']=='failed'
        with pytest.raises(HandoffError):resume(order['work_order_id'],settings,'operator',journal,client,URL,True)


def test_changed_order_identity_never_posts(assignment,tmp_path):
    _,settings,order,_,_=assignment
    journal=Journal(tmp_path/'private')
    journal.write({'version':1,'order':order,'owner':'operator','controller':URL,'submission':'accepted','task_id':TASK})
    order['objective']='Changed instruction'
    with connection(lambda request:pytest.fail('must not post')) as client:
        with pytest.raises(HandoffError,match='identity_conflict'):submit(order,settings,'operator',journal,client,URL)


def test_symlink_parent_rejected_before_creating_directory(tmp_path):
    destination=tmp_path/'actual';destination.mkdir()
    link=tmp_path/'alias';link.symlink_to(destination,target_is_directory=True)
    with pytest.raises(HandoffError):Journal(link/'journal')
    assert not (destination/'journal').exists()


def test_native_journal_submit_and_validation_use_controller_snapshot(assignment,tmp_path):
    root,settings,order,_,execution=assignment
    journal=Journal(tmp_path/'private');calls=[]
    execution.update(id=TASK,work_order_id=order['work_order_id'],snapshot=order['source'],
                     validation={'structure_valid':True,'source_valid':True,'review_required':True})
    def server(request):
        calls.append(request.url.path)
        if request.method=='POST':
            assert json.loads(request.content)==order
            return httpx.Response(202,json={'id':TASK,'status':'queued'})
        return httpx.Response(200,json=execution)
    with connection(server) as client:
        submit(order,settings,'operator',journal,client,URL,native=True)
        (root/'source.py').write_text('changed after capture')
        assert resume(order['work_order_id'],settings,'operator',journal,client,URL,True)['validation']['source_valid']
        with pytest.raises(HandoffError,match='identity_conflict'):submit(order,settings,'operator',journal,client,URL)
    assert calls==['/v1/work-orders','/v1/tasks/'+TASK]
