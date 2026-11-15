"""Verify an extracted project-history package; never import or execute its contents."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

JSON_LIMIT = 16 * 1024 * 1024


def package_path(value):
    if not isinstance(value, str) or not value or '\0' in value or '\\' in value:
        raise ValueError('Invalid package path')
    path = PurePosixPath(value)
    if (path.is_absolute() or not path.parts or '..' in path.parts
            or path.as_posix() != value):
        raise ValueError('Package paths must be canonical and relative')
    return path


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate manifest key')
            result[key] = value
        return result
    with path.open('rb') as stream:
        data = stream.read(JSON_LIMIT + 1)
    if len(data) > JSON_LIMIT:
        raise ValueError('Package manifest exceeds size limit')
    return json.loads(data, object_pairs_hook=unique)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def fingerprint(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return {'kind':'symlink', 'target':os.readlink(path)}
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('Package contains a special or hard-linked file')
    return {'kind':'file', 'sha256':digest(path), 'size':info.st_size,
            'executable':bool(info.st_mode & 0o111)}


def package_entries(base):
    pending = [base]
    entries = {}
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as scan:
            for entry in scan:
                path = Path(entry.path)
                relative = path.relative_to(base).as_posix()
                package_path(relative)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                else:
                    entries[relative] = path
                    if len(entries) > 100000:
                        raise ValueError('Too many package files')
    return entries


def verify(base, checksums_sha256):
    base = base.expanduser().absolute()
    mode = base.lstat().st_mode
    if (base.resolve() != base or not stat.S_ISDIR(mode) or mode & 0o077):
        raise ValueError('Package must be a canonical owner-only directory')
    if not isinstance(checksums_sha256, str) or not re.fullmatch('[0-9a-f]{64}', checksums_sha256):
        raise ValueError('Supply the trusted SHA-256 of checksums.json')
    checksum_file = base/'checksums.json'
    info = checksum_file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > JSON_LIMIT:
        raise ValueError('Invalid checksums file')
    if digest(checksum_file) != checksums_sha256:
        raise ValueError('Checksums file does not match the trusted digest')
    checksums = read_json(checksum_file)
    if not isinstance(checksums, dict) or not checksums or len(checksums) > 100000:
        raise ValueError('Invalid package checksums')
    for relative, expected in checksums.items():
        package_path(relative)
        if not isinstance(expected, dict):
            raise ValueError('Invalid file fingerprint')
        if expected.get('kind') == 'file':
            if (set(expected) != {'kind','sha256','size','executable'}
                    or not isinstance(expected['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', expected['sha256'])
                    or type(expected['size']) is not int or expected['size'] < 0
                    or type(expected['executable']) is not bool):
                raise ValueError('Invalid regular file fingerprint')
        elif expected.get('kind') == 'symlink':
            if set(expected) != {'kind','target'} or not isinstance(expected['target'], str):
                raise ValueError('Invalid symlink fingerprint')
        else:
            raise ValueError('Unknown file fingerprint')
    entries = package_entries(base)
    if set(entries) != set(checksums) | {'checksums.json'} or 'checksums.json' in checksums:
        raise ValueError('Package file inventory differs from checksums')
    for relative, expected in checksums.items():
        if fingerprint(entries[relative]) != expected:
            raise ValueError('Package fingerprint mismatch')
    manifest_file = entries.get('manifest.json')
    if manifest_file is None or checksums['manifest.json']['kind'] != 'file':
        raise ValueError('Manifest must be a verified regular file')
    manifest = read_json(manifest_file)
    if (not isinstance(manifest, dict) or type(manifest.get('version')) is not int
            or manifest['version'] != 1 or not isinstance(manifest.get('checkouts'), list)):
        raise ValueError('Unsupported project package manifest')
    seen = set()
    for checkout in manifest['checkouts']:
        if not isinstance(checkout, dict):
            raise ValueError('Invalid checkout record')
        name = checkout.get('id')
        if (not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', name)
                or name in seen):
            raise ValueError('Invalid or duplicate checkout ID')
        seen.add(name)
        if not isinstance(checkout.get('files'), dict):
            raise ValueError('Invalid working-file manifest')
        for relative, expected in checkout['files'].items():
            path = package_path(relative)
            if '.git' in path.parts:
                raise ValueError('Working files must not include Git metadata')
            if checksums.get('checkouts/'+name+'/'+relative) != expected:
                raise ValueError('Working-file manifest differs from transport inventory')
        prefix = 'checkouts/'+name+'/.git/'
        if not any(relative.startswith(prefix) for relative in checksums):
            raise ValueError('Checkout has no preserved Git metadata')
    # Recheck manifests after validation. This is not a lock against concurrent writers.
    if digest(checksum_file) != checksums_sha256 or digest(manifest_file) != checksums['manifest.json']['sha256']:
        raise ValueError('Package manifests changed during verification')
    return {'verified':True, 'package_version':1, 'checkouts':len(seen),
            'files_checked':len(checksums), 'checksums_sha256':checksums_sha256,
            'git_history_checked':False, 'imported':False, 'runtime_grants_changed':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--checksums-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.package, args.checksums_sha256)))


if __name__ == '__main__':
    main()
