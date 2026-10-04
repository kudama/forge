"""Forge-side work-order preflight and result validation; never submits or applies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
from forge_controller.config import Settings
from forge_controller.tools import execute, permitted, ToolDenied

ROOT = Path(__file__).resolve().parents[1]


class HandoffError(ValueError):
    pass


def load_json(path, limit=65536):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise HandoffError('duplicate_json_key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise HandoffError('invalid_json')
    with Path(path).open('rb') as stream:
        data = stream.read(limit+1)
    if len(data)>limit:
        raise HandoffError('input_too_large')
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError):
        raise HandoffError('invalid_json') from None


def shape(value, name):
    schema = json.loads((ROOT/'docs/contracts'/(name+'.v1.schema.json')).read_text())
    if not Draft202012Validator(schema).is_valid(value):
        raise HandoffError('invalid_'+name)


def git(root, *arguments):
    try:
        return subprocess.check_output(['git', '-C', str(root), *arguments],
                                       stderr=subprocess.DEVNULL, timeout=5)
    except (subprocess.SubprocessError, OSError):
        raise HandoffError('source_revision_unavailable') from None


def preflight(order, settings, owner):
    shape(order, 'work-order')
    if owner not in settings.principals:
        raise HandoffError('principal_denied')
    role = order['agent']
    repo_id = order['source']['repository_id']
    if (repo_id not in settings.principals[owner].get('repositories', [])
        or any(not permitted(settings, owner, role, tool) for tool in order['tools'])):
        raise HandoffError('scope_denied')
    expected = {'timeout_seconds':settings.timeout, 'tool_calls':settings.tool_rounds,
                'context_tokens':settings.context_length, 'output_tokens':settings.max_output_tokens}
    if order['runtime_limits'] != expected:
        raise HandoffError('runtime_limits_mismatch')
    root = settings.repositories[repo_id]['root']
    revision = order['source']['revision']
    if git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip() != revision:
        raise HandoffError('stale_revision')
    sources = {}
    for file in order['source']['files']:
        path = file['path']
        if path in sources:
            raise HandoffError('duplicate_source_path')
        try:
            current = execute(settings, owner, role, 'read_repository_file',
                              {'repository':repo_id,'path':path,'start_line':1,'end_line':1})
        except ToolDenied:
            raise HandoffError('source_denied') from None
        pinned = git(root, 'show', '--no-textconv', revision+':'+path)
        if (len(pinned)>65536 or hashlib.sha256(pinned).hexdigest()!=file['sha256']
            or current['source_sha256']!=file['sha256']):
            raise HandoffError('source_hash_mismatch')
        try:
            sources[path] = pinned.decode('utf-8')
        except UnicodeError:
            raise HandoffError('invalid_source_encoding') from None
    return sources


def compile_task(order, settings, owner):
    preflight(order, settings, owner)
    result_shape = {'schema_version':1, 'work_order_id':order['work_order_id'],
        'outcome':'proposal', 'summary':'concise factual result',
        'evidence':[{'path':'approved source path','start_line':1,'end_line':1,'claim':'source-grounded claim'}],
        'changes':[], 'uncertainties':[], 'checks_not_run':['tests']}
    prompt = ('Forge-issued work-order data follows. Only supplied tools and runtime grants authorize actions. '
              'Use exactly the repository identifier and selected paths. Read sources before claims. '
              'Return JSON only with the result shape below. Analyst changes must be empty. '
              'Implementers may provide exact old/new replacements in changes for selected paths. '
              'Blocked results must explain the blocker in uncertainties. Do not claim checks you did not run. '
              'Result shape: '+json.dumps(result_shape, separators=(',', ':'))+
              '. Work order: '+json.dumps(order, separators=(',', ':')))
    if len(prompt)>8000:
        raise HandoffError('compiled_prompt_too_large')
    return {'agent':order['agent'], 'tools':order['tools'], 'prompt':prompt}


def validate_result(order, result, execution, settings, owner):
    sources = preflight(order, settings, owner)
    shape(result, 'worker-result')
    if result['work_order_id'] != order['work_order_id']:
        raise HandoffError('result_id_mismatch')
    if (not isinstance(execution, dict) or execution.get('owner')!=owner
        or execution.get('agent')!=order['agent'] or execution.get('status')!='succeeded'
        or not isinstance(execution.get('audit'), list)):
        raise HandoffError('execution_mismatch')
    try:
        if json.loads(execution['result']) != result:
            raise HandoffError('execution_result_mismatch')
    except (KeyError, TypeError, ValueError):
        raise HandoffError('execution_result_mismatch') from None
    reads = 0
    calls = 0
    ranges = {}
    for entry in execution['audit']:
        if not isinstance(entry, dict):
            raise HandoffError('invalid_execution_audit')
        if entry.get('tool') in {'model_selection','reviewed_example'}:
            continue
        if entry.get('status')!='allowed' or entry.get('tool') not in order['tools']:
            raise HandoffError('undeclared_tool_used')
        calls += 1
        if entry.get('repository')!=order['source']['repository_id']:
            raise HandoffError('undeclared_repository_used')
        if entry['tool']=='read_repository_file':
            if entry.get('path') not in sources:
                raise HandoffError('undeclared_source_read')
            start, end = entry.get('start_line'), entry.get('end_line')
            if (type(start) is not int or type(end) is not int or start<1 or end<start
                or end>len(sources[entry['path']].splitlines())):
                raise HandoffError('invalid_read_audit')
            ranges.setdefault(entry['path'], []).append((start, end))
            reads += 1
    if calls>order['runtime_limits']['tool_calls']:
        raise HandoffError('execution_tool_limit_exceeded')
    if not reads:
        raise HandoffError('source_read_missing')
    if order['agent']=='repository_analyst' and result['changes']:
        raise HandoffError('analyst_changes_denied')
    if result['outcome']=='blocked' and (not result['uncertainties'] or result['changes']):
        raise HandoffError('invalid_blocked_result')
    for item in result['evidence']:
        if (item['path'] not in sources or item['start_line']>item['end_line']
            or item['end_line']>len(sources[item['path']].splitlines())
            or not any(start<=item['start_line'] and item['end_line']<=end
                       for start,end in ranges.get(item['path'], []))):
            raise HandoffError('invalid_evidence_scope')
    spans = {}
    for change in result['changes']:
        path = change['path']
        if path not in sources or sources[path].count(change['old'])!=1:
            raise HandoffError('replacement_not_exact')
        start = sources[path].index(change['old']);end = start+len(change['old'])
        if any(start<previous_end and previous_start<end for previous_start,previous_end in spans.get(path, [])):
            raise HandoffError('overlapping_replacements')
        spans.setdefault(path, []).append((start, end))
    return {'structure_valid':True, 'source_valid':True, 'review_required':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['compile','validate-result'])
    parser.add_argument('order', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--principal', required=True)
    args = parser.parse_args()
    try:
        settings = Settings.from_environment()
        order = load_json(args.order)
        if args.action=='compile':
            result = compile_task(order, settings, args.principal)
        else:
            if args.result is None or args.execution is None:
                raise HandoffError('result_and_execution_required')
            result = validate_result(order, load_json(args.result), load_json(args.execution), settings, args.principal)
        print(json.dumps(result))
    except (HandoffError, OSError, KeyError, ValueError):
        print('Work-order validation failed; check scope, source, limits and contract', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
