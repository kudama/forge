import json
from pathlib import Path, PurePosixPath

import pytest

from scripts import project_package as package


@pytest.mark.parametrize('value', ['', '.', '..', '../file', '/file', 'a/../b',
    './a', 'a/./b', 'a//b', 'a/', 'a\\b', '\0', None, 3])
def test_package_paths_reject_ambiguous_and_escaping_names(value):
    with pytest.raises(ValueError):package.package_path(value)


@pytest.mark.parametrize('value', ['.git/config', 'folder/file.', '書籍/notes.md'])
def test_package_paths_preserve_legitimate_names(value):
    assert package.package_path(value) == PurePosixPath(value)


@pytest.fixture
def exported(tmp_path):
    base = tmp_path/'package';base.mkdir(mode=0o700)
    checkout = base/'checkouts/01-example';checkout.mkdir(parents=True)
    (checkout/'.git').mkdir()
    (checkout/'.git/HEAD').write_text('ref: refs/heads/main\n')
    (checkout/'file.txt').write_text('private working content')
    (checkout/'link').symlink_to('/outside/not-read')
    manifest = {'version':1, 'checkouts':[{'id':'01-example', 'files':{
        name:package.fingerprint(checkout/name) for name in ('file.txt','link')}}]}
    (base/'manifest.json').write_text(json.dumps(manifest))
    return base


def seal(base):
    checksums = {str(path.relative_to(base)):package.fingerprint(path)
        for path in base.rglob('*') if (path.is_file() or path.is_symlink())
        and path.name != 'checksums.json'}
    path = base/'checksums.json';path.write_text(json.dumps(checksums))
    return package.digest(path)


def snapshot(base):
    return {str(path.relative_to(base)):(path.lstat().st_mode,
        path.read_bytes() if path.is_file() and not path.is_symlink() else None)
        for path in [base, *base.rglob('*')]}


def test_verification_is_read_only_and_reports_its_boundary(exported):
    trusted = seal(exported);before = snapshot(exported)
    result = package.verify(exported, trusted)
    assert result == {'verified':True, 'package_version':1, 'checkouts':1,
        'files_checked':4, 'checksums_sha256':trusted, 'git_history_checked':False,
        'imported':False, 'runtime_grants_changed':False}
    assert snapshot(exported) == before
    assert 'private working content' not in json.dumps(result)


@pytest.mark.parametrize('change', ['extra','missing','content','mode','hardlink','directory_link'])
def test_transport_changes_are_rejected_before_import(exported, change):
    trusted = seal(exported)
    file = exported/'checkouts/01-example/file.txt'
    if change == 'extra':(exported/'extra').write_text('not listed')
    elif change == 'missing':file.unlink()
    elif change == 'content':file.write_text('changed')
    elif change == 'mode':file.chmod(0o700)
    elif change == 'hardlink':(exported/'extra').hardlink_to(file)
    else:
        metadata = exported/'checkouts/01-example/.git'
        moved = exported.parent/'outside';metadata.rename(moved)
        metadata.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError):package.verify(exported, trusted)


def test_symlink_fingerprint_never_opens_target(exported, monkeypatch):
    trusted = seal(exported)
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path.name != 'link'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    assert package.verify(exported, trusted)['verified']


@pytest.mark.parametrize('change', ['escape','duplicate_id','manifest_symlink','mismatch','bool_size'])
def test_invalid_package_structure_is_rejected(exported, change):
    manifest_file = exported/'manifest.json'
    manifest = json.loads(manifest_file.read_text())
    if change == 'escape':manifest['checkouts'][0]['id'] = '../outside'
    elif change == 'duplicate_id':manifest['checkouts'] *= 2
    elif change == 'mismatch':manifest['checkouts'][0]['files']['file.txt']['size'] = 1
    elif change == 'manifest_symlink':
        moved = exported.parent/'manifest.json';manifest_file.rename(moved)
        manifest_file.symlink_to(moved)
    if change != 'manifest_symlink':manifest_file.write_text(json.dumps(manifest))
    trusted = seal(exported)
    if change == 'bool_size':
        checksums = json.loads((exported/'checksums.json').read_text())
        checksums['checkouts/01-example/file.txt']['size'] = True
        (exported/'checksums.json').write_text(json.dumps(checksums))
        trusted = package.digest(exported/'checksums.json')
    with pytest.raises(ValueError):package.verify(exported, trusted)


def test_resealed_tampering_does_not_match_original_trust_anchor(exported):
    trusted = seal(exported)
    (exported/'checkouts/01-example/file.txt').write_text('tampered')
    seal(exported)
    with pytest.raises(ValueError, match='trusted digest'):package.verify(exported, trusted)


def test_duplicate_checksum_keys_are_rejected(exported):
    seal(exported)
    path = exported/'checksums.json';path.write_text('{"a":{},"a":{}}')
    with pytest.raises(ValueError, match='Duplicate'):package.verify(exported, package.digest(path))


@pytest.mark.parametrize('change', ['symlink','public','bad_digest'])
def test_unsafe_package_root_or_anchor_is_rejected(exported, change):
    trusted = seal(exported)
    if change == 'symlink':
        link = exported.parent/'link';link.symlink_to(exported, target_is_directory=True)
        exported = link
    elif change == 'public':exported.chmod(0o755)
    else:trusted = 'not-a-digest'
    with pytest.raises(ValueError):package.verify(exported, trusted)
