"""Generate proposals through the real controller; never execute model output.

Run from the repository root with .venv/bin/python evals/coding/run.py MODEL.
Senior review must approve each candidate before isolated test execution.
"""
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx

from forge_controller.app import create_app
from forge_controller.config import Settings


FILES = ['src/forge_controller/model.py', 'src/forge_controller/config.py',
         'tests/test_model_limits.py', 'pyproject.toml']
CASES = [
    ('patch', 'Read model.py lines 1–40. Propose exactly one edit changing keep_alive from 5m to 2m, preserving everything else. Return only JSON {"path":"src/forge_controller/model.py","edits":[{"before":"exact existing text","after":"replacement text"}]}. Preserve source indentation and real JSON escaping.'),
    ('test', 'Read model.py lines 1–40 and tests/test_model_limits.py lines 1–80. Return only JSON {"path":"tests/test_candidate.py","content":"complete Python test source"}. Write one meaningful async pytest test using the actual Ollama and Settings APIs and httpx.MockTransport. Verify Ollama.chat raises ModelError with model_unavailable when upstream returns HTTP 503. Close clients. Do not invent helpers or execute anything.'),
    ('bug', 'Read config.py lines 20–35. This isolated copy contains a seeded validation bug: context_length accepts booleans. Propose the smallest correct edit that rejects booleans while preserving acceptance of positive exact integers and rejection of zero, negatives, floats, strings and None. Return only JSON {"path":"src/forge_controller/config.py","edits":[{"before":"exact existing text","after":"replacement text"}]}. Do not change max_output_tokens or unrelated code.'),
]


async def main(model):
    root = Path.cwd().resolve()
    report = {'model': model, 'base_source_sha256': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in FILES},
              'method': 'one attempt per case; references disabled; cold loading included; generated code never executed by this runner',
              'context_length': 4096, 'max_output_tokens': 1024, 'cases': []}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:11434', trust_env=False) as runtime:
        report['manifest'] = next(m for m in (await runtime.get('/api/tags')).json()['models'] if m['name']==model)
    for kind, prompt in CASES:
        prompt = 'Use read_repository_file with repository="forge" and full paths src/forge_controller/model.py, src/forge_controller/config.py, tests/test_model_limits.py as relevant. You must call the tool before answering. ' + prompt
        with tempfile.TemporaryDirectory(prefix='forge-coding-') as directory:
            fixture = Path(directory).resolve()
            for path in FILES:
                (fixture/path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root/path, fixture/path)
            if kind == 'bug':
                path = fixture/FILES[1]
                source = path.read_text()
                assert source.count('type(self.context_length) is not int') == 1
                path.write_text(source.replace('type(self.context_length) is not int', 'not isinstance(self.context_length, int)', 1))
            settings = Settings(database=fixture/'tasks.sqlite3', model=model, timeout=180,
                context_length=4096, max_output_tokens=1024, tool_rounds=8,
                principals={'tester': {'token':'e'*40, 'agents':['implementer'], 'services':[], 'repositories':['forge']}},
                repositories={'forge': {'root':str(fixture), 'files':FILES}})
            app = create_app(settings)
            start = time.monotonic()
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://evaluation', headers={'Authorization':'Bearer '+'e'*40}) as client:
                    response = await client.post('/v1/tasks', json={'agent':'implementer', 'prompt':prompt, 'tools':['list_repository_files','read_repository_file']})
                    response.raise_for_status()
                    task_id = response.json()['id']
                    while True:
                        task = (await client.get('/v1/tasks/'+task_id)).json()
                        if task['status'] in {'succeeded','failed','cancelled'}:
                            break
                        if time.monotonic()-start > 190:
                            raise TimeoutError('Controller did not settle')
                        await asyncio.sleep(.1)
            report['cases'].append({'case':kind, 'prompt':prompt, 'elapsed_seconds':round(time.monotonic()-start,2),
                'fixture_sha256':{p:hashlib.sha256((fixture/p).read_bytes()).hexdigest() for p in FILES},
                'task':task, 'manual_review_required':True})
            async with httpx.AsyncClient(base_url=settings.model_url, trust_env=False) as runtime:
                report['cases'][-1]['loaded_models'] = (await runtime.get('/api/ps')).json()
            target = root/'state'/('coding-'+model.replace(':','-')+'.json')
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report,indent=2)+'\n')
            print(kind, task['status'], report['cases'][-1]['elapsed_seconds'], flush=True)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:11434', timeout=60, trust_env=False) as runtime:
        await runtime.post('/api/generate',json={'model':model,'keep_alive':0})


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
