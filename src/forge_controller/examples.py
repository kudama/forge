"""Small, manually reviewed reference corpus; no model-generated auto-promotion."""
import hashlib
import json
import re
import stat
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tools import execute, ToolDenied


class Example(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    status: Literal['approved']
    agent: Literal['repository_analyst', 'implementer']
    repository: str = Field(min_length=1, max_length=64)
    reviewer: str = Field(min_length=1, max_length=100)
    reviewed_on: str
    source_hashes: dict[str, str] = Field(min_length=1, max_length=5)
    terms: list[str] = Field(min_length=1, max_length=20)
    lesson: str = Field(min_length=1, max_length=1200)


def load_examples(path: Path | None):
    if path is None:
        return [], None
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o022:
        raise ValueError('Reviewed corpus must be regular and not group/world writable')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Reviewed corpus exceeds 64 KiB')
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) > 50:
        raise ValueError('Reviewed corpus must contain at most 50 examples')
    examples = [Example.model_validate(record) for record in records]
    if len({e.id for e in examples}) != len(examples):
        raise ValueError('Duplicate reviewed example ID')
    for example in examples:
        date.fromisoformat(example.reviewed_on)
        if any(not re.fullmatch(r'[0-9a-f]{64}', digest) for digest in example.source_hashes.values()):
            raise ValueError('Invalid source hash')
        if any(not re.fullmatch(r'[a-z0-9_]+', term) for term in example.terms):
            raise ValueError('Terms must be lowercase single words')
    return examples, hashlib.sha256(raw).hexdigest()


def retrieve(examples, settings, owner, agent, prompt):
    """Filter by current permissions and source revision before lexical ranking."""
    words = set(re.findall(r'[a-z0-9_]+', prompt.casefold()))
    candidates = []
    for example in examples:
        score = len(words.intersection(example.terms))
        if example.agent != agent or not score:
            continue
        try:
            for path, digest in example.source_hashes.items():
                result = execute(settings, owner, agent, 'read_repository_file', {
                    'repository': example.repository, 'path': path, 'start_line': 1, 'end_line': 1})
                if result['source_sha256'] != digest:
                    raise ToolDenied()
        except ToolDenied:
            continue
        candidates.append((score, example.id, example))
    chosen, size = [], 0
    for _, _, example in sorted(candidates, key=lambda item: (-item[0], item[1])):
        record = {'id': example.id, 'repository': example.repository,
                  'source_hashes': example.source_hashes, 'lesson': example.lesson}
        encoded = json.dumps(record, ensure_ascii=True)
        if len(chosen) >= 2 or size + len(encoded) > 2200:
            continue
        chosen.append(record)
        size += len(encoded)
    return chosen
