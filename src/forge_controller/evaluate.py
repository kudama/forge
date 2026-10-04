"""Repeatable mechanical checks, not an autonomous correctness/promotion judge."""
import argparse
import ast
import asyncio
import hashlib
import json
import re
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import httpx

from .app import create_app
from .config import Settings
from .tools import execute, ToolDenied


READ_TOOLS = ['list_repository_files', 'read_repository_file']


def assess(case, task, settings, owner):
    result = task.get('result') or ''
    reads = {a.get('path') for a in task['audit'] if a['tool'] == 'read_repository_file' and a['status'] == 'allowed'}
    checks = {'task_succeeded': task['status'] == 'succeeded',
              'required_sources_read': set(case['required_reads']).issubset(reads)}
    if case['kind'] == 'limits':
        checks['named_defaults'] = all(word in result for word in ['context_length', '4096', 'max_output_tokens', '512'])
        checks['source_citation_format'] = bool(re.search(r'src/forge_controller/config\.py:\d+', result))
        checks['cited_defaults_match_source'] = False
        try:
            source = execute(settings, owner, case['agent'], 'read_repository_file', {
                'repository': 'forge', 'path': 'src/forge_controller/config.py', 'start_line': 1, 'end_line': 80})
            lines = {int(line.split(': ', 1)[0]): line.split(': ', 1)[1] for line in source['content'].splitlines()}
            cited = [int(n) for n in re.findall(r'src/forge_controller/config\.py:(\d+)', result)]
            checks['cited_defaults_match_source'] = bool(cited) and all(n in lines for n in cited) and all(
                any(field in lines[n] and value in lines[n] for n in cited) for field, value in [('context_length','4096'),('max_output_tokens','512')])
        except (ToolDenied, ValueError):
            pass
    elif case['kind'] == 'integer_review':
        checks['bool_pitfall_named'] = 'bool' in result.casefold() and 'isinstance' in result
        checks['bool_acceptance_explained'] = bool(re.search(r'(?:accept(?:s|ing)?|allow(?:s|ing)?)\s+(?:boolean|bool)s?', result.casefold())) or ('isinstance(True, int)' in result and bool(re.search(r'returns\s+`?true', result.casefold())))
        checks['exact_type_proposed'] = bool(re.search(r'type\([^)]*\)\s+is\s+(?:not\s+)?int', result))
        checks['invalid_cases_named'] = all(word in result.casefold() for word in ['zero', 'negative', 'float'])
        checks['no_known_false_float_claim'] = not bool(re.search(r'floats?\s+(?:are\s+)?(?:already\s+)?(?:rejected|excluded)\s+by\s+`?value\s*>\s*0', result.casefold()))
    elif case['kind'] == 'temperature_patch':
        checks['exact_applicable_patch'] = False
        try:
            patch = json.loads(result)
            if set(patch) != {'path', 'edits'} or patch['path'] != 'src/forge_controller/model.py' or len(patch['edits']) != 1:
                raise ValueError('Wrong patch scope')
            edit = patch['edits'][0]
            if set(edit) != {'before', 'after'} or not all(isinstance(edit[k], str) and edit[k] for k in edit):
                raise ValueError('Invalid edit')
            source = execute(settings, owner, case['agent'], 'read_repository_file', {
                'repository': 'forge', 'path': patch['path'], 'start_line': 1, 'end_line': 80})
            if source['total_lines'] > 80:
                raise ValueError('Fixture exceeds checker scope')
            text = '\n'.join(line.split(': ', 1)[1] for line in source['content'].splitlines()) + '\n'
            if text.count(edit['before']) != 1 or text.count('temperature=0') != 1:
                raise ValueError('Patch does not match exact fixture')
            candidate = text.replace(edit['before'], edit['after'], 1)
            ast.parse(candidate)  # Parse only. Never execute generated code.
            checks['exact_applicable_patch'] = candidate == text.replace('temperature=0', 'temperature=0.1', 1)
        except (ValueError, TypeError, KeyError, SyntaxError, ToolDenied):
            pass
    else:
        raise ValueError('Unknown evaluation kind')
    return checks


async def run_suite(settings, owner, cases, mode, adapter=None):
    if owner not in settings.principals:
        raise ValueError('Unknown evaluation principal')
    if mode not in {'off', 'on'}:
        raise ValueError('Invalid reference mode')
    config = replace(settings, examples_file=settings.examples_file if mode == 'on' else None)
    if mode == 'on' and config.examples_file is None:
        raise ValueError('Reference-enabled evaluation requires FORGE_EXAMPLES_FILE')
    rows = []
    with tempfile.TemporaryDirectory(prefix='forge-eval-') as directory:
        config = replace(config, database=Path(directory)/'tasks.sqlite3')
        app = create_app(config, adapter)
        async with app.router.lifespan_context(app):
            corpus_hash = app.state.engine.corpus_hash
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://evaluation',
                                         headers={'Authorization': 'Bearer ' + config.principals[owner]['token']}) as client:
                for case in cases:
                    start = time.monotonic()
                    response = await client.post('/v1/tasks', json={'agent': case['agent'], 'prompt': case['prompt'], 'tools': READ_TOOLS})
                    response.raise_for_status()
                    task_id = response.json()['id']
                    while True:
                        response = await client.get('/v1/tasks/' + task_id)
                        response.raise_for_status()
                        task = response.json()
                        if task['status'] in {'succeeded', 'failed', 'cancelled'}:
                            break
                        if time.monotonic() - start > config.timeout + 5:
                            await client.post('/v1/tasks/' + task_id + '/cancel')
                            raise TimeoutError('Evaluation exceeded its controller deadline')
                        await asyncio.sleep(.05)
                    checks = assess(case, task, config, owner)
                    rows.append({'case': case['id'], 'agent': case['agent'], 'model': config.model_for(case['agent']), 'status': task['status'], 'error': task['error'],
                                 'elapsed_seconds': round(time.monotonic()-start, 2), 'checks': checks,
                                 'mechanical_pass': all(checks.values()), 'manual_review_required': True,
                                 'result': task['result'], 'audit': task['audit']})
    return {'reference_mode': mode, 'corpus_sha256': corpus_hash, 'model': config.model,
            'role_models': config.role_models,
            'context_length': config.context_length, 'max_output_tokens': config.max_output_tokens,
            'tool_call_limit': config.tool_rounds, 'cases': rows}


def load_cases(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Case file exceeds 64 KiB')
    cases = json.loads(raw)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError('Expected 1–20 cases')
    ids = set()
    for case in cases:
        if set(case) != {'id', 'agent', 'kind', 'prompt', 'required_reads'} or case['id'] in ids:
            raise ValueError('Invalid or duplicate evaluation case')
        if case['agent'] not in {'repository_analyst', 'implementer'} or case['kind'] not in {'limits', 'integer_review', 'temperature_patch'}:
            raise ValueError('Unsupported evaluation case')
        if not isinstance(case['prompt'], str) or not 1 <= len(case['prompt']) <= 8000 or not isinstance(case['required_reads'], list) or not case['required_reads']:
            raise ValueError('Invalid evaluation input')
        ids.add(case['id'])
    return cases, hashlib.sha256(raw).hexdigest()


async def evaluate(args):
    config = Settings.from_environment()
    cases, cases_hash = load_cases(args.cases)
    async with httpx.AsyncClient(base_url=config.model_url, timeout=10, trust_env=False) as runtime:
        response = await runtime.get('/api/tags')
        response.raise_for_status()
        installed = {item['name']: item for item in response.json()['models']}
        required = {config.model_for(case['agent']) for case in cases}
        if not required.issubset(installed):
            raise ValueError('An evaluation role model is not installed')
        manifests = {name: installed[name] for name in sorted(required)}
    source_hashes = {}
    for case in cases:
        for path in case['required_reads']:
            read = execute(config, args.principal, case['agent'], 'read_repository_file', {
                'repository': 'forge', 'path': path, 'start_line': 1, 'end_line': 1})
            source_hashes[path] = read['source_sha256']
    modes = ['off', 'on'] if args.references == 'both' else [args.references]
    report = {'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases_sha256': cases_hash, 'source_sha256': source_hashes, 'model_manifests': manifests,
              'method': 'sequential single runs; wall times include loading/caching; mechanical checks require senior review', 'runs': []}
    for mode in modes:
        report['runs'].append(await run_suite(config, args.principal, cases, mode))
    report['source_stable'] = all(execute(config, args.principal, next(case['agent'] for case in cases if path in case['required_reads']), 'read_repository_file', {'repository':'forge', 'path':path, 'start_line':1, 'end_line':1})['source_sha256'] == digest for path,digest in source_hashes.items())
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2)+'\n')
    for run in report['runs']:
        passed = sum(row['mechanical_pass'] for row in run['cases'])
        print(f"References {run['reference_mode']}: {passed}/{len(run['cases'])} mechanical checks passed; senior review required.")
    return 0 if report['source_stable'] and all(row['mechanical_pass'] for run in report['runs'] for row in run['cases']) else 1


def main():
    parser = argparse.ArgumentParser(description='Run bounded local Forge evaluation cases')
    parser.add_argument('--cases', default='evals/cases.json')
    parser.add_argument('--principal', default='mike')
    parser.add_argument('--references', choices=['off', 'on', 'both'], default='both')
    parser.add_argument('--output', default='state/evaluation.json')
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))


if __name__ == '__main__':
    main()
