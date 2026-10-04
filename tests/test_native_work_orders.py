import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import pytest
from tests.test_work_orders import assignment as source_assignment
from tests.test_controller import terminal
from forge_controller.app import create_app
from forge_controller.store import Store


@pytest.fixture
def assignment(source_assignment):
    source_assignment[1].principals['operator']['agents'].append('forge')
    return source_assignment


class Worker:
    def __init__(self,result,path='source.py',wait=False):
        self.result=result;self.path=path;self.wait=wait
        self.started=asyncio.Event();self.release=asyncio.Event();self.outputs=[]
    async def ready(self):return True
    async def close(self):pass
    async def chat(self,messages,tools,**kwargs):
        self.started.set()
        if self.wait:await self.release.wait()
        if messages[-1]['role']!='tool':
            return {'tool_calls':[{'function':{'name':'list_repository_files','arguments':{'repository':'forge'}}}]}
        self.outputs.append(json.loads(messages[-1]['content']))
        if 'files' in self.outputs[-1]:
            return {'tool_calls':[{'function':{'name':'read_repository_file','arguments':{
                'repository':'forge','path':self.path,'start_line':1,'end_line':3}}}]}
        return {'content':json.dumps(self.result)}


@asynccontextmanager
async def instance(settings,model):
    app=create_app(settings,model)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test',headers={'Authorization':'Bearer '+'t'*40}) as client:
            yield client,app


async def test_native_snapshot_survives_checkout_changes_and_scopes_listing(assignment):
    root,settings,order,result,_=assignment
    (root/'other.py').write_text('forbidden')
    settings.repositories['forge']['files'].append('other.py')
    order['tools'].append('list_repository_files')
    model=Worker(result,wait=True)
    async with instance(settings,model) as (client,app):
        receipt=await client.post('/v1/work-orders',json=order)
        assert receipt.status_code==202
        task=receipt.json()['id'];await model.started.wait()
        (root/'source.py').write_text('mutated after admission')
        model.release.set()
        row=await terminal(client,task)
        assert row['status']=='succeeded',row
        assert model.outputs[0]['files']==['source.py']
        assert 'first' in model.outputs[1]['content'] and 'mutated' not in model.outputs[1]['content']
        assert row['snapshot']==order['source'] and row['validation']['review_required']
        captured=app.state.store.db.execute('SELECT sources_json FROM work_orders WHERE task_id=?',(task,)).fetchone()[0]
        assert json.loads(captured)['source.py']=='first\nsecond\nthird\n'


async def test_manifest_file_outside_selected_scope_denied(assignment):
    root,settings,order,result,_=assignment
    (root/'other.py').write_text('forbidden');settings.repositories['forge']['files'].append('other.py')
    order['tools'].append('list_repository_files')
    async with instance(settings,Worker(result,path='other.py')) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        row=await terminal(client,task)
        assert row['status']=='failed' and row['error']=='tool_denied'


@pytest.mark.parametrize('mutation',['unknown','hash','revision','role','tools','limits','path'])
async def test_invalid_native_admission(assignment,mutation):
    _,settings,order,result,_=assignment
    if mutation=='unknown':order['extra']=True
    elif mutation=='hash':order['source']['files'][0]['sha256']='0'*64
    elif mutation=='revision':order['source']['revision']='0'*40
    elif mutation=='role':settings.principals['operator']['agents']=[]
    elif mutation=='tools':order['tools']=['execute_commands']
    elif mutation=='limits':order['runtime_limits']['output_tokens']+=1
    else:order['source']['files'][0]['path']='../secret.py'
    model=Worker(result)
    async with instance(settings,model) as (client,app):
        assert (await client.post('/v1/work-orders',json=order)).status_code==(403 if mutation=='role' else 422)
        assert not model.started.is_set()
        assert app.state.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0


@pytest.mark.parametrize('mutation',['id','unknown','citation','patch'])
async def test_invalid_native_result_fails(assignment,mutation):
    _,settings,order,result,_=assignment
    order['tools'].append('list_repository_files')
    if mutation=='id':result['work_order_id']='0'*32
    elif mutation=='unknown':result['extra']=True
    elif mutation=='citation':result['evidence'][0]['path']='other.py'
    else:result['changes']=[{'path':'source.py','old':'first','new':'changed'}]
    async with instance(settings,Worker(result)) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        row=await terminal(client,task)
        assert row['status']=='failed' and row['error']=='invalid_worker_result'
        assert row['validation']['structure_valid'] is False


async def test_duplicate_tombstone_owner_and_restart(assignment):
    _,settings,order,result,_=assignment
    order['tools'].append('list_repository_files')
    async with instance(settings,Worker(result)) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        assert (await terminal(client,task))['status']=='succeeded'
        assert (await client.post('/v1/work-orders',json=order)).status_code==409
        assert (await client.get('/v1/tasks/'+task,headers={'Authorization':''})).status_code==401
        assert (await client.delete('/v1/tasks/'+task)).status_code==204
        assert app.state.store.db.execute('SELECT sources_json FROM work_orders').fetchone()==(None,)
    async with instance(settings,Worker(result)) as (client,app):
        assert (await client.post('/v1/work-orders',json=order)).status_code==409
        assert (await client.get('/v1/tasks/'+task)).status_code==404


def test_version_one_database_migrates_without_losing_tasks(tmp_path):
    path=tmp_path/'tasks.sqlite3'
    store=Store(path);task=store.create('owner','forge');store.update(task,'succeeded',result='kept')
    store.db.execute('DROP TABLE work_orders');store.db.execute('PRAGMA user_version=1');store.db.commit();store.close()
    restored=Store(path)
    try:
        assert restored.get(task)['result']=='kept'
        assert restored.db.execute('PRAGMA user_version').fetchone()[0]==2
    finally:restored.close()


def test_packaged_contracts_match_documented_contracts():
    import forge_controller.work_orders as contracts
    for name in ['work-order','worker-result']:
        assert json.loads((contracts.ROOT/'contracts'/(name+'.v1.schema.json')).read_text())==json.loads(Path('docs/contracts/'+name+'.v1.schema.json').read_text())


async def test_cancel_restart_and_backup_preserve_native_binding(assignment,tmp_path):
    _,settings,order,result,_=assignment
    order['tools'].append('list_repository_files')
    worker=Worker(result,wait=True)
    async with instance(settings,worker) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        await worker.started.wait()
        assert (await client.post('/v1/tasks/'+task+'/cancel')).json()['status']=='cancelled'
        assert (await terminal(client,task))['status']=='cancelled'
        import sqlite3
        with sqlite3.connect(tmp_path/'restored.sqlite3') as target:app.state.store.db.backup(target)
    restored=Store(tmp_path/'restored.sqlite3')
    try:
        assert restored.get(task)['work_order_id']==order['work_order_id']
        assert restored.has_order('operator',order['work_order_id'])
        assert restored.db.execute('SELECT sources_json FROM work_orders').fetchone()[0]
    finally:restored.close()


async def test_cross_owner_cannot_read_native_task(assignment):
    _,settings,order,result,_=assignment
    settings.principals['other']={'token':'u'*40,'agents':['repository_analyst'],'services':[],'repositories':['forge']}
    order['tools'].append('list_repository_files')
    async with instance(settings,Worker(result)) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        for path in ['/v1/tasks/'+task,'/v1/tasks/'+task+'/cancel']:
            method=client.post if path.endswith('cancel') else client.get
            assert (await method(path,headers={'Authorization':'Bearer '+'u'*40})).status_code==404


async def test_native_mcp_submission(assignment,tmp_path):
    from mcp import Client
    from forge_controller.mcp_bridge import BridgeSettings,create_bridge
    _,settings,order,result,_=assignment
    order['tools'].append('list_repository_files')
    token=tmp_path/'token.json';token.write_text(json.dumps({'token':'t'*40}));token.chmod(0o600)
    async with instance(settings,Worker(result)) as (_,app):
        async with Client(create_bridge(BridgeSettings(token),transport=httpx.ASGITransport(app))) as client:
            receipt=await client.call_tool('forge_submit_work_order',{'order':order})
            assert not receipt.is_error
            assert len(receipt.structured_content['id'])==32


async def test_interrupted_native_task_is_not_replayed_on_restart(assignment):
    _,settings,order,result,_=assignment
    order['tools'].append('list_repository_files')
    worker=Worker(result,wait=True)
    async with instance(settings,worker) as (client,app):
        task=(await client.post('/v1/work-orders',json=order)).json()['id']
        await worker.started.wait()
    replacement=Worker(result)
    async with instance(settings,replacement) as (client,app):
        row=(await client.get('/v1/tasks/'+task)).json()
        assert row['status']=='failed' and row['error']=='interrupted'
        assert row['work_order_id']==order['work_order_id']
        assert not replacement.started.is_set()
        assert (await client.post('/v1/work-orders',json=order)).status_code==409


async def test_worker_only_principal_cannot_issue_orders(assignment):
    _,settings,order,result,_=assignment
    settings.principals['operator']['agents'].remove('forge')
    async with instance(settings,Worker(result)) as (client,app):
        assert (await client.post('/v1/work-orders',json=order)).status_code==403
        assert app.state.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
