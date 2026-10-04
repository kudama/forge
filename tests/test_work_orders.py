import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
pytest.importorskip('jsonschema')  # Included in the optional MCP tooling lock.
from scripts.work_orders import HandoffError, compile_task, load_json, validate_result
from forge_controller.config import Settings


@pytest.fixture
def assignment(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    (root/'source.py').write_text('first\nsecond\nthird\n')
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid',
                    'commit','-qm','fixture'],check=True)
    config=Settings(database=tmp_path/'tasks.sqlite3',principals={'operator':{
        'token':'t'*40,'agents':['repository_analyst','implementer'],'services':[],'repositories':['forge']}},
        repositories={'forge':{'root':str(root.resolve()),'files':['source.py']}})
    order=json.loads(Path('docs/contracts/work-order.v1.example.json').read_text())
    order['source']={'repository_id':'forge','revision':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
        'files':[{'path':'source.py','sha256':hashlib.sha256((root/'source.py').read_bytes()).hexdigest()}]}
    order['runtime_limits']={'timeout_seconds':60,'tool_calls':3,'context_tokens':4096,'output_tokens':512}
    result={'schema_version':1,'work_order_id':order['work_order_id'],'outcome':'proposal',
        'summary':'Source contains first','evidence':[{'path':'source.py','start_line':1,'end_line':1,'claim':'first'}],
        'changes':[],'uncertainties':[],'checks_not_run':['tests']}
    execution={'owner':'operator','agent':'repository_analyst','status':'succeeded','result':json.dumps(result),
        'audit':[{'tool':'read_repository_file','status':'allowed','repository':'forge','path':'source.py','start_line':1,'end_line':3}]}
    return root,config,order,result,execution


def test_valid_compile_and_result_remain_review_required(assignment):
    _,config,order,result,execution=assignment
    task=compile_task(order,config,'operator')
    assert task['agent']=='repository_analyst' and task['tools']==['read_repository_file']
    assert len(task['prompt'])<=8000 and 't'*40 not in task['prompt']
    assert validate_result(order,result,execution,config,'operator')['review_required'] is True


@pytest.mark.parametrize('kind',['unknown','revision','hash','path','duplicate','limits','grants'])
def test_invalid_assignment_rejected(assignment,kind):
    root,config,order,_,_=assignment
    if kind=='unknown':order['extra']=True
    elif kind=='revision':order['source']['revision']='0'*40
    elif kind=='hash':(root/'source.py').write_text('changed')
    elif kind=='path':order['source']['files'][0]['path']='../source.py'
    elif kind=='duplicate':order['source']['files'].append({**order['source']['files'][0],'sha256':'0'*64})
    elif kind=='limits':order['runtime_limits']['tool_calls']=2
    else:config.principals['operator']['repositories']=[]
    with pytest.raises(HandoffError):compile_task(order,config,'operator')


@pytest.mark.parametrize('kind',['id','unknown','path','range','changes','blocked','owner','audit','result'])
def test_invalid_result_or_execution_rejected(assignment,kind):
    _,config,order,result,execution=assignment
    if kind=='id':result['work_order_id']='0'*32
    elif kind=='unknown':result['extra']=1
    elif kind=='path':result['evidence'][0]['path']='other.py'
    elif kind=='range':result['evidence'][0]['end_line']=10
    elif kind=='changes':result['changes']=[{'path':'source.py','old':'first','new':'updated'}]
    elif kind=='blocked':result['outcome']='blocked'
    elif kind=='owner':execution['owner']='other'
    elif kind=='audit':execution['audit'][0]['path']='other.py'
    else:execution['result']='{}'
    if kind!='result':execution['result']=json.dumps(result)
    with pytest.raises(HandoffError):validate_result(order,result,execution,config,'operator')


def test_exact_implementer_replacements_and_overlap(assignment):
    _,config,order,result,execution=assignment
    order['agent']=execution['agent']='implementer'
    result['changes']=[{'path':'source.py','old':'first','new':'updated'}]
    execution['result']=json.dumps(result)
    assert validate_result(order,result,execution,config,'operator')['review_required']
    result['changes'].append({'path':'source.py','old':'first\nsecond','new':'replaced'})
    execution['result']=json.dumps(result)
    with pytest.raises(HandoffError,match='overlapping'):validate_result(order,result,execution,config,'operator')


def test_source_drift_rejected_at_result_review(assignment):
    root,config,order,result,execution=assignment
    (root/'source.py').write_text('changed')
    with pytest.raises(HandoffError):validate_result(order,result,execution,config,'operator')


@pytest.mark.parametrize('data',[b'{"a":1,"a":2}',b'{"a":NaN}',b'x'*65537])
def test_bounded_strict_json_loading(tmp_path,data):
    path=tmp_path/'input.json';path.write_bytes(data)
    with pytest.raises(HandoffError):load_json(path)


@pytest.mark.parametrize('kind',['principal','role','file','symlink'])
def test_preflight_permissions_and_unsafe_sources(assignment,kind):
    root,config,order,_,_=assignment
    owner='operator'
    if kind=='principal':owner='other'
    elif kind=='role':config.principals['operator']['agents']=['forge']
    elif kind=='file':order['source']['files'][0]['path']='unapproved.py'
    else:
        (root/'source.py').unlink();(root/'source.py').symlink_to(root/'outside.py')
    with pytest.raises(HandoffError):compile_task(order,config,owner)


@pytest.mark.parametrize('kind',['tool','repository','no_read','failed'])
def test_result_requires_allowed_successful_source_execution(assignment,kind):
    _,config,order,result,execution=assignment
    if kind=='tool':execution['audit'][0]['tool']='shell'
    elif kind=='repository':execution['audit'][0]['repository']='other'
    elif kind=='no_read':execution['audit']=[]
    else:execution['status']='failed'
    with pytest.raises(HandoffError):validate_result(order,result,execution,config,'operator')


def test_long_work_order_is_not_silently_truncated(assignment):
    _,config,order,_,_=assignment
    order['objective']='x'*2000
    order['acceptance_criteria']=[str(i)+'x'*499 for i in range(8)]
    # Additional schema-valid issue URL length pushes the compiled prompt over its limit.
    order['issue_url']='https://github.com/'+'x'*1000+'/repo/issues/1'
    with pytest.raises(HandoffError,match='compiled_prompt_too_large'):
        compile_task(order,config,'operator')


@pytest.mark.parametrize('kind',['unread_lines','bad_range','too_many_calls'])
def test_citations_must_match_audited_read_ranges_and_budget(assignment,kind):
    _,config,order,result,execution=assignment
    if kind=='unread_lines':execution['audit'][0]['start_line']=2
    elif kind=='bad_range':execution['audit'][0]['start_line']=True
    else:execution['audit']*=4
    with pytest.raises(HandoffError):validate_result(order,result,execution,config,'operator')
