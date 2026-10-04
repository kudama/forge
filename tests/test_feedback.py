import hashlib
import json

import pytest

from forge_controller.examples import load_examples, retrieve
from forge_controller.evaluate import assess, run_suite
from forge_controller.store import Store
from test_repository_tools import settings
from test_controller import FakeModel


def record(config, **overrides):
    root=config.repositories['forge']['root']
    from pathlib import Path
    source=(Path(root)/'source.py').read_bytes()
    item={'id':'reviewed-integer','status':'approved','agent':'repository_analyst','repository':'forge',
          'reviewer':'Senior Forge','reviewed_on':'2026-10-03',
          'source_hashes':{'source.py':hashlib.sha256(source).hexdigest()},
          'terms':['integer','bool'],'lesson':'Actual integers require type(value) is int; reject bool.'}
    item.update(overrides)
    return item


def corpus(tmp_path, config, **overrides):
    path=tmp_path/'reviewed.json'
    path.write_text(json.dumps([record(config,**overrides)]))
    path.chmod(0o644)
    return path


def test_retrieval_permission_relevance_and_staleness(tmp_path):
    config=settings(tmp_path)
    records,digest=load_examples(corpus(tmp_path,config))
    assert len(digest)==64
    assert len(retrieve(records,config,'mike','repository_analyst','integer bool'))==1
    assert retrieve(records,config,'other','repository_analyst','integer bool')==[]
    assert retrieve(records,config,'mike','implementer','integer bool')==[]
    assert retrieve(records,config,'mike','repository_analyst','unrelated')==[]
    from pathlib import Path
    (Path(config.repositories['forge']['root'])/'source.py').write_text('changed')
    assert retrieve(records,config,'mike','repository_analyst','integer bool')==[]


@pytest.mark.parametrize('bad',[{'status':'draft'},{'source_hashes':{'source.py':'bad'}},{'reviewed_on':'bad'}, {'terms':['two words']},{'unknown':'x'}])
def test_unapproved_invalid_records_rejected(tmp_path,bad):
    config=settings(tmp_path)
    with pytest.raises(ValueError):
        load_examples(corpus(tmp_path,config,**bad))


def test_corpus_permissions_duplicates_and_budget(tmp_path):
    config=settings(tmp_path)
    path=corpus(tmp_path,config);path.chmod(0o666)
    with pytest.raises(ValueError):load_examples(path)
    path.chmod(0o644)
    path.write_text(json.dumps([record(config),record(config)]))
    with pytest.raises(ValueError):load_examples(path)
    records=[]
    for n in range(5):
        item=record(config,id='review-'+str(n),lesson='x'*1100)
        from forge_controller.examples import Example
        records.append(Example.model_validate(item))
    chosen=retrieve(records,config,'mike','repository_analyst','integer')
    assert len(chosen)<=2
    assert sum(len(json.dumps(item)) for item in chosen)<=2200


async def test_reference_injection_and_audit(tmp_path):
    from dataclasses import replace
    config=settings(tmp_path)
    config=replace(config,examples_file=corpus(tmp_path,config),tool_rounds=1)
    class Reader(FakeModel):
        async def chat(self,messages,tools):
            assert 'reviewed-integer' in messages[1]['content']
            if messages[-1]['role']=='tool':
                return {'content':'bool type(value) is int; reject zero negative float'}
            return {'content':'','tool_calls':[{'function':{'name':'read_repository_file','arguments':{'repository':'forge','path':'source.py','start_line':1,'end_line':1}}}]}
    case={'id':'integer','agent':'repository_analyst','kind':'integer_review','prompt':'integer bool isinstance','required_reads':['source.py']}
    run=await run_suite(config,'mike',[case],'on',Reader())
    row=run['cases'][0]
    assert row['status']=='succeeded'  # reference retrieval doesn't consume tool budget
    assert row['audit'][0]['example_id']=='reviewed-integer'
    assert row['manual_review_required'] is True
    assert row['mechanical_pass'] is False  # missing isinstance in answer is detected
    assert config.database.exists() is False  # evaluation uses its own temporary DB


async def test_startup_failure_releases_store(tmp_path):
    from dataclasses import replace
    from forge_controller.app import create_app
    config=settings(tmp_path)
    config=replace(config,examples_file=corpus(tmp_path,config,status='draft'))
    app=create_app(config,FakeModel())
    with pytest.raises(ValueError):
        async with app.router.lifespan_context(app):pass
    store=Store(config.database)
    store.close()


def test_checker_rejects_failed_task_and_unread_sources(tmp_path):
    config=settings(tmp_path)
    task={'status':'failed','result':'context_length 4096 max_output_tokens 512 src/forge_controller/config.py:1','audit':[]}
    checks=assess({'kind':'limits','agent':'repository_analyst','required_reads':['source.py']},task,config,'mike')
    assert checks['task_succeeded'] is False
    assert checks['required_sources_read'] is False


def test_known_false_float_claim_is_not_a_pass(tmp_path):
    config=settings(tmp_path)
    case={'kind':'integer_review','required_reads':['source.py']}
    task={'status':'succeeded','result':'isinstance accepts bool. Use type(value) is int. Zero, negative, floats are already rejected by value > 0.',
          'audit':[{'tool':'read_repository_file','status':'allowed','path':'source.py'}]}
    assert assess(case,task,config,'mike')['no_known_false_float_claim'] is False


def test_patch_checker_checks_exact_scope_without_execution(tmp_path):
    from pathlib import Path
    config=settings(tmp_path)
    config.principals['mike']['agents']=['implementer']
    path='src/forge_controller/model.py'
    source=Path(config.repositories['forge']['root'])/path
    source.parent.mkdir(parents=True)
    source.write_text('payload = dict(temperature=0)\n')
    config.repositories['forge']['files']=[path]
    task={'status':'succeeded','audit':[{'tool':'read_repository_file','status':'allowed','path':path}]}
    case={'kind':'temperature_patch','agent':'implementer','required_reads':[path]}
    task['result']=json.dumps({'path':path,'edits':[{'before':'temperature=0','after':'temperature=0.1'}]})
    assert assess(case,task,config,'mike')['exact_applicable_patch'] is True
    task['result']=json.dumps({'path':path,'edits':[{'before':'temperature=0','after':'__import__("os").system("false")'}]})
    assert assess(case,task,config,'mike')['exact_applicable_patch'] is False
    task['result']='not JSON'
    assert assess(case,task,config,'mike')['exact_applicable_patch'] is False


def test_false_boolean_rejection_claim_fails(tmp_path):
    config=settings(tmp_path)
    case={'kind':'integer_review','required_reads':['source.py']}
    task={'status':'succeeded','result':'isinstance would reject bool and float. type(value) is int also rejects zero and negative values.',
          'audit':[{'tool':'read_repository_file','status':'allowed','path':'source.py'}]}
    assert assess(case,task,config,'mike')['bool_acceptance_explained'] is False


def test_citations_are_checked_against_source(tmp_path):
    from pathlib import Path
    config=settings(tmp_path)
    path='src/forge_controller/config.py'
    source=Path(config.repositories['forge']['root'])/path
    source.parent.mkdir(parents=True)
    source.write_text('context_length: int = 4096\nmax_output_tokens: int = 512\n')
    config.repositories['forge']['files']=[path]
    case={'kind':'limits','agent':'repository_analyst','required_reads':[path]}
    task={'status':'succeeded','audit':[{'tool':'read_repository_file','status':'allowed','path':path}],
          'result':f'context_length 4096 {path}:1; max_output_tokens 512 {path}:2'}
    assert assess(case,task,config,'mike')['cited_defaults_match_source'] is True
    task['result']=f'context_length 4096 max_output_tokens 512 {path}:999'
    assert assess(case,task,config,'mike')['cited_defaults_match_source'] is False
