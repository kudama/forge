"""Fetch hash-pinned official Checkmk sources for offline API tests, never production."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen


def fetch(destination):
    lock = json.loads(Path(__file__).with_name('api-source.lock.json').read_text())
    def one(item):
        path, digest = item
        target = destination / path
        data = target.read_bytes() if target.exists() else urlopen(
            f'https://raw.githubusercontent.com/{lock["repository"]}/{lock["commit"]}/{path}', timeout=30).read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Checkmk API source digest mismatch: ' + path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, lock['files'].items()))
    print('Verified official Checkmk API source files:', len(lock['files']))


if __name__ == '__main__':
    fetch(Path(sys.argv[1]))
