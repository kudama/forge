"""A 'line' is LF-terminated, exactly as git, editors and reviewers count it."""
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from forge_controller.tools import execute_snapshot, split_lines
from forge_controller.work_orders import HandoffError, preflight, validate_snapshot_result
from tests.test_work_orders import assignment  # noqa: F401  (fixture)

# Characters str.splitlines() treats as line breaks but git and editors do not.
SPLITLINES_ONLY = ['\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029']


@pytest.mark.parametrize('text,expected', [
    ('', []), ('a', ['a']), ('a\n', ['a']), ('a\n\n', ['a', '']), ('\n', ['']),
    ('a\nb', ['a', 'b']), ('a\r\nb\r\n', ['a\r', 'b\r']),
])
def test_split_lines_basic_shapes(text, expected):
    assert split_lines(text) == expected


@pytest.mark.parametrize('char', SPLITLINES_ONLY)
def test_split_lines_ignores_non_lf_separators(char):
    text = f'one{char}still one\ntwo\n'
    assert split_lines(text) == [f'one{char}still one', 'two']
    assert len(text.splitlines()) != len(split_lines(text))  # the bug this guards against


def settings():
    return SimpleNamespace(principals={'mike': {'agents': ['implementer'], 'repositories': ['r'], 'services': []}})


def read(source, start, end):
    order = {'tools': ['read_repository_file'], 'source': {'repository_id': 'r'}}
    return execute_snapshot(settings(), 'mike', 'implementer', 'read_repository_file',
                            {'repository': 'r', 'path': 'a.py', 'start_line': start, 'end_line': end},
                            order, {'a.py': source})


@pytest.mark.parametrize('char', SPLITLINES_ONLY)
def test_snapshot_line_numbers_match_git(tmp_path, char):
    source = f'first\n# page{char}break\nMARKER\nlast\n'
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'a.py').write_bytes(source.encode())
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'a.py'], check=True)
    git_line = int(subprocess.check_output(
        ['git', '-C', str(tmp_path), 'grep', '-n', '--cached', 'MARKER'], text=True).split(':')[1])
    result = read(source, 1, 80)
    shown = {int(row.split(': ', 1)[0]) for row in result['content'].split('\n') if row.endswith('MARKER')}
    assert shown == {git_line} == {3}
    assert result['total_lines'] == 4


def test_result_evidence_cannot_cite_a_line_past_the_real_end(assignment):  # noqa: F811
    _, _, order, result, execution = assignment
    source = 'a\n\x0c\nc\nd\n'                      # 4 real lines; splitlines() would say 5
    sources = {'source.py': source}
    execution['audit'] = [{'tool': 'read_repository_file', 'status': 'allowed', 'repository': 'forge',
                           'path': 'source.py', 'start_line': 1, 'end_line': 4}]
    result['evidence'][0].update(start_line=4, end_line=4)
    execution['result'] = json.dumps(result)
    assert validate_snapshot_result(order, result, execution, sources, 'operator')['source_valid']
    result['evidence'][0].update(start_line=4, end_line=5)
    execution['result'] = json.dumps(result)
    with pytest.raises(HandoffError, match='invalid_evidence_scope'):
        validate_snapshot_result(order, result, execution, sources, 'operator')


def commit(root, data):
    (root / 'source.py').write_bytes(data)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=T', '-c', 'user.email=t@example.invalid',
                    'commit', '-qm', 'x'], check=True)
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def test_crlf_source_is_refused_with_an_explicit_reason(assignment):  # noqa: F811
    root, config, order, _, _ = assignment
    data = b'def f():\r\n    return 1\r\n'
    order['source']['revision'] = commit(root, data)
    order['source']['files'][0]['sha256'] = hashlib.sha256(data).hexdigest()
    with pytest.raises(HandoffError, match='unsupported_line_endings'):
        preflight(order, config, 'operator')


def test_lf_source_still_passes_preflight(assignment):  # noqa: F811
    root, config, order, _, _ = assignment
    data = b'def f():\n    return 1\n'
    order['source']['revision'] = commit(root, data)
    order['source']['files'][0]['sha256'] = hashlib.sha256(data).hexdigest()
    assert preflight(order, config, 'operator') == {'source.py': data.decode()}
