import ast
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from scripts import setup


@pytest.fixture
def checkout(tmp_path):
    root=tmp_path/'checkout';root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nrequires-python = ">=3.12"\n')
    (root/'requirements.lock').write_text('core fixture\n')
    (root/'requirements-mcp.lock').write_text('-r requirements.lock\nmcp fixture\n')
    return root


@pytest.fixture
def runner(checkout,monkeypatch):
    calls=[]
    fail={'pytest':False}
    executable=checkout.parent/'python3.12';executable.touch()
    def run(command,**kwargs):
        calls.append(command)
        assert 'shell' not in kwargs
        if '-c' in command:
            venv=Path(command[0]).parent.parent==checkout/'.venv'
            prefix=str(checkout/'.venv') if venv else '/runtime'
            return SimpleNamespace(returncode=0,stdout=json.dumps({'version':[3,12,16],
                'executable':command[0],'prefix':prefix,'base_prefix':'/runtime'}))
        if command[1:3]==['-m','venv']:
            path=Path(command[3])/'bin/python';path.parent.mkdir(parents=True);path.touch()
        if command[1:]==['-m','pytest','-q'] and fail['pytest']:
            raise subprocess.CalledProcessError(1,command)
        return SimpleNamespace(returncode=0,stdout='pip 26.0.1 from /runtime/pip\n')
    monkeypatch.setattr(setup.subprocess,'run',run)
    return executable,calls,fail


def test_new_install_orders_packaging_full_lock_editable_and_checks(checkout,runner):
    executable,calls,_=runner
    result=setup.install(checkout,executable)
    assert result['tests_passed'] and not result['services_changed']
    steps=[call[1:] for call in calls if len(call)>2 and call[1]=='-m' and call[2]!='venv']
    assert steps==[['-m','pip','install','--upgrade','pip','setuptools','wheel'],
                   ['-m','pip','install','-r',str(checkout/'requirements-mcp.lock')],
                   ['-m','pip','install','--no-deps','-e',str(checkout)],
                   ['-m','pip','check'],['-m','pytest','-q']]
    assert not (checkout/'.secrets').exists() and not (checkout/'state').exists()
    count=len(calls)
    assert setup.install(checkout,executable)['status']=='already-installed'
    assert all('-c' in call for call in calls[count:])


def test_failed_install_retains_files_and_can_resume_same_command(checkout,runner):
    executable,calls,fail=runner;fail['pytest']=True
    with pytest.raises(subprocess.CalledProcessError):setup.install(checkout,executable)
    marker=checkout/'.venv'/setup.MARKER
    assert json.loads(marker.read_text())['phase']=='incomplete'
    sentinel=checkout/'.venv/keep';sentinel.write_text('preserve')
    fail['pytest']=False
    assert setup.install(checkout,executable)['status']=='installed'
    assert sentinel.read_text()=='preserve'
    assert sum(call[1:3]==['-m','venv'] for call in calls)==1


@pytest.mark.parametrize('existing',['foreign','symlink','private_state','changed_locks','marker_symlink','invalid_marker'])
def test_refuses_conflicting_state_without_replacement(checkout,runner,existing):
    executable,calls,_=runner
    if existing=='foreign':
        (checkout/'.venv').mkdir();(checkout/'.venv/keep').write_text('important')
    elif existing=='symlink':
        other=checkout.parent/'other';other.mkdir();(checkout/'.venv').symlink_to(other)
    elif existing=='private_state':(checkout/'state').mkdir()
    elif existing=='marker_symlink':
        (checkout/'.venv').mkdir();(checkout/'.venv'/setup.MARKER).symlink_to(executable)
    elif existing=='invalid_marker':
        (checkout/'.venv').mkdir();(checkout/'.venv'/setup.MARKER).write_text('[]')
    else:
        setup.install(checkout,executable)
        (checkout/'requirements-mcp.lock').write_text('different requirements')
    before={str(p.relative_to(checkout)):p.read_bytes() for p in checkout.rglob('*') if p.is_file() and not p.is_symlink()}
    with pytest.raises(ValueError):setup.install(checkout,executable)
    after={str(p.relative_to(checkout)):p.read_bytes() for p in checkout.rglob('*') if p.is_file() and not p.is_symlink()}
    assert before==after


@pytest.mark.parametrize('data',[[],{}, {'version':[True,12,0],'executable':'p','prefix':'/p','base_prefix':'/p'},
    {'version':[3,12],'executable':'p','prefix':'/p','base_prefix':'/p'},
    {'version':[3,12,0],'executable':None,'prefix':'/p','base_prefix':'/p'}])
def test_probe_rejects_malformed_fields_and_boolean_version(monkeypatch,data):
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=json.dumps(data)))
    with pytest.raises(ValueError):setup.python_info('/explicit/python')


def test_old_python_cannot_create_environment(checkout,monkeypatch):
    monkeypatch.setattr(setup,'python_info',lambda path:{'version':[3,9,6]})
    with pytest.raises(ValueError,match='Unsupported Python'):setup.install(checkout,Path('/system/python'))
    assert not (checkout/'.venv').exists()


def test_probe_does_not_resolve_venv_symlink(checkout,monkeypatch):
    base=checkout.parent/'base-python';base.touch()
    link=checkout.parent/'venv-python';link.symlink_to(base)
    commands=[]
    def run(command,**kwargs):
        commands.append(command)
        assert kwargs['timeout']==10 and kwargs['check'] is True
        return SimpleNamespace(stdout=json.dumps({'version':[3,12,0],'executable':str(link),
            'prefix':'/venv','base_prefix':'/runtime'}))
    monkeypatch.setattr(setup.subprocess,'run',run)
    setup.python_info(link)
    assert commands[0][0]==str(link)


def test_preflight_reports_absent_tools_and_old_python_without_writes(checkout,monkeypatch):
    monkeypatch.setattr(setup,'python_info',lambda path:{'version':[3,9,6],
        'executable':'/system/python','prefix':'/system','base_prefix':'/system'})
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='pip 21.2.4 from /system/pip'))
    monkeypatch.setattr(setup,'ollama_status',lambda:{'executable':None,'reachable':False,'models':[]})
    monkeypatch.setattr(setup,'service_status',lambda:{'controller':{'loaded':False}})
    monkeypatch.setattr(setup,'port_status',lambda:{'8787':{'occupied':False}})
    before=sorted(str(p) for p in checkout.rglob('*'))
    result=setup.check(checkout,Path('/system/python'))
    assert not result['environment_ready']
    assert result['selected_python']['pip_version']=='21.2.4'
    assert any('explicit supported interpreter' in action for action in result['actions'])
    assert before==sorted(str(p) for p in checkout.rglob('*'))


def test_bootstrap_source_is_parseable_by_python39():
    ast.parse(Path(setup.__file__).read_text(),feature_version=(3,9))
