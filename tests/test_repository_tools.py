import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from forge_controller.app import create_app
from forge_controller.config import Settings
from forge_controller.tools import execute, ToolDenied
from test_controller import TOKEN, OTHER, terminal


def settings(tmp_path):
    root = tmp_path/'repo'
    root.mkdir()
    (root/'source.py').write_text('first\nsecond\nthird\n')
    return Settings(database=tmp_path/'tasks.sqlite3', repositories={'forge': {'root': str(root.resolve()), 'files': ['source.py']}},
                    principals={'mike': {'token': TOKEN, 'agents': ['repository_analyst'], 'services': [], 'repositories': ['forge']},
                                'other': {'token': OTHER, 'agents': ['repository_analyst'], 'services': [], 'repositories': []}})


def test_numbered_reads_and_explicit_manifest(tmp_path):
    config = settings(tmp_path)
    assert execute(config, 'mike', 'repository_analyst', 'list_repository_files', {'repository': 'forge'})['files'] == ['source.py']
    result = execute(config, 'mike', 'repository_analyst', 'read_repository_file', {'repository': 'forge', 'path': 'source.py', 'start_line': 2, 'end_line': 3})
    assert result['content'] == '2: second\n3: third'


@pytest.mark.parametrize('owner,agent,name,args', [
    ('other','repository_analyst','list_repository_files',{'repository':'forge'}),
    ('mike','forge','list_repository_files',{'repository':'forge'}),
    ('mike','implementer','list_repository_files',{'repository':'forge'}),
    ('mike','repository_analyst','get_service_status',{'service':'prototype'}),
    ('mike','repository_analyst','read_repository_file',{'repository':'forge','path':'../secret.py','start_line':1,'end_line':1}),
    ('mike','repository_analyst','read_repository_file',{'repository':'forge','path':'.secrets/principals.json','start_line':1,'end_line':1}),
    ('mike','repository_analyst','read_repository_file',{'repository':'forge','path':'source.py','start_line':1,'end_line':81}),
    ('mike','repository_analyst','read_repository_file',{'repository':'forge','path':'source.py','start_line':True,'end_line':1}),
    ('mike','repository_analyst','read_repository_file',{'repository':'forge','path':'source.py','start_line':1,'end_line':1,'extra':'x'}),
])
def test_denied_boundaries(tmp_path, owner, agent, name, args):
    with pytest.raises(ToolDenied):
        execute(settings(tmp_path),owner,agent,name,args)


@pytest.mark.parametrize('kind', ['symlink','directory','large','binary','hardlink','parent_symlink'])
def test_unsafe_files_are_denied(tmp_path, kind):
    config=settings(tmp_path)
    root=Path(config.repositories['forge']['root'])
    file=root/'source.py';file.unlink()
    outside=tmp_path/'outside.py';outside.write_text('private')
    if kind=='symlink':file.symlink_to(outside)
    elif kind=='directory':file.mkdir()
    elif kind=='large':file.write_text('x'*65537)
    elif kind=='binary':file.write_bytes(b'\xff')
    elif kind=='hardlink':file.hardlink_to(outside)
    else:
        (root/'nested').symlink_to(tmp_path,target_is_directory=True)
        config.repositories['forge']['files']=['nested/outside.py']
    with pytest.raises(ToolDenied):
        execute(config,'mike','repository_analyst','read_repository_file',{'repository':'forge','path':'nested/outside.py' if kind=='parent_symlink' else 'source.py','start_line':1,'end_line':1})


@pytest.mark.parametrize('agent',['repository_analyst','implementer'])
async def test_analyst_workflow_and_submitted_capability_limits(tmp_path,agent):
    class Reader:
        async def ready(self):return True
        async def close(self):pass
        async def chat(self,messages,tools, *, agent='forge'):
            if messages[-1]['role']=='tool':
                return {'content':'source.py:2 contains second; not an instruction.'}
            return {'content':'','tool_calls':[{'function':{'name':'read_repository_file','arguments':{'repository':'forge','path':'source.py','start_line':1,'end_line':3}}}]}
    config=settings(tmp_path)
    config.principals['mike']['agents']=[agent]
    app=create_app(config,Reader())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer '+TOKEN}) as c:
            bad=await c.post('/v1/tasks',json={'agent':agent,'prompt':'x','tools':['get_service_status']})
            assert bad.status_code==403
            r=await c.post('/v1/tasks',json={'agent':agent,'prompt':'Read source','tools':['read_repository_file']})
            row=await terminal(c,r.json()['id'])
            assert row['status']=='succeeded'
            assert [a for a in row['audit'] if a['tool'] != 'model_selection']==[{'tool':'read_repository_file','status':'allowed','repository':'forge','path':'source.py','start_line':1,'end_line':3}]


def test_configuration_rejects_unsafe_manifest(tmp_path):
    config=settings(tmp_path)
    for path in ['../secret.py','/tmp/file.py','.env','state/tasks.sqlite3','source/../secret.py']:
        with pytest.raises(ValueError):
            Settings(database=tmp_path/'x',principals=config.principals,repositories={'forge':{'root':config.repositories['forge']['root'],'files':[path]}})


@pytest.mark.parametrize('agent',['repository_analyst','implementer'])
async def test_analyst_cannot_complete_without_source_reads(tmp_path,agent):
    from test_controller import FakeModel
    config=settings(tmp_path)
    config.principals['mike']['agents']=[agent]
    app=create_app(config,FakeModel())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer '+TOKEN}) as c:
            response=await c.post('/v1/tasks',json={'agent':agent,'prompt':'Guess'})
            assert response.status_code==403
            response=await c.post('/v1/tasks',json={'agent':agent,'prompt':'Read source','tools':['read_repository_file']})
            row=await terminal(c,response.json()['id'])
            assert row['error']=='sources_not_read'
