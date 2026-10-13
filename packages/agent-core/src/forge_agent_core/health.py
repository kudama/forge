"""Metadata-only health snapshots and Checkmk local-check output; no probes."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat

from .core import decode, encode

SAFE = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
STATES = {'ok', 'degraded', 'failed', 'unknown'}
LIMIT = 8192


def name(value):
    if not isinstance(value, str) or not SAFE.fullmatch(value):
        raise ValueError('invalid_health_name')
    return value


@dataclass(frozen=True)
class Snapshot:
    agent_id: str
    instance_id: str
    version: str
    observed_at: datetime
    alive: bool
    accepting_work: bool
    dependencies: tuple[tuple[str, str], ...]

    def __post_init__(self):
        name(self.agent_id); name(self.instance_id)
        if not isinstance(self.version, str) or not VERSION.fullmatch(self.version):
            raise ValueError('invalid_health_version')
        if (not isinstance(self.observed_at, datetime) or self.observed_at.utcoffset() is None
                or type(self.alive) is not bool or type(self.accepting_work) is not bool):
            raise ValueError('invalid_health_state')
        dependencies = tuple(tuple(item) for item in self.dependencies)
        if len(dependencies) > 32:
            raise ValueError('too_many_dependencies')
        seen = set()
        for item in dependencies:
            if len(item) != 2:
                raise ValueError('invalid_dependency')
            key, state = item
            name(key)
            if key in seen or state not in STATES:
                raise ValueError('invalid_dependency')
            seen.add(key)
        object.__setattr__(self, 'dependencies', dependencies)

    def as_dict(self):
        return dict(schema_version=1, agent_id=self.agent_id, instance_id=self.instance_id,
                    version=self.version, observed_at=self.observed_at.astimezone(timezone.utc).isoformat(),
                    alive=self.alive, accepting_work=self.accepting_work, dependencies=dict(self.dependencies))

    def to_json(self):
        value = encode(self.as_dict())
        if len(value.encode()) > LIMIT:
            raise ValueError('health_size_limit')
        return value

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, (bytes, str)) or len(raw if isinstance(raw, bytes) else raw.encode()) > LIMIT:
            raise ValueError('health_size_limit')
        value = decode(raw)
        fields = {'schema_version', 'agent_id', 'instance_id', 'version', 'observed_at',
                  'alive', 'accepting_work', 'dependencies'}
        if (type(value) is not dict or set(value) != fields
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or type(value['dependencies']) is not dict or not isinstance(value['observed_at'], str)):
            raise ValueError('invalid_health_snapshot')
        return cls(value['agent_id'], value['instance_id'], value['version'],
                   datetime.fromisoformat(value['observed_at']), value['alive'],
                   value['accepting_work'], tuple(value['dependencies'].items()))


@dataclass(frozen=True)
class Policy:
    agent_id: str
    instance_id: str
    required_dependencies: frozenset[str] = frozenset()
    max_age_seconds: int = 180

    def __post_init__(self):
        name(self.agent_id); name(self.instance_id)
        required = frozenset(self.required_dependencies)
        if len(required) > 32:
            raise ValueError('too_many_dependencies')
        for key in required:
            name(key)
        if type(self.max_age_seconds) is not int or not 1 <= self.max_age_seconds <= 86400:
            raise ValueError('invalid_health_max_age')
        object.__setattr__(self, 'required_dependencies', required)


def render(policy, snapshot=None, *, now=None, unavailable='snapshot_unavailable'):
    """Two stable services. Required dependencies come from trusted collector config."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('timezone_required')
    live = ready = 3
    summary = unavailable if unavailable in {'snapshot_unavailable', 'snapshot_invalid'} else 'snapshot_invalid'
    live_summary = ready_summary = summary
    metric = '-'
    if snapshot is not None:
        age = (now - snapshot.observed_at).total_seconds()
        if snapshot.agent_id != policy.agent_id or snapshot.instance_id != policy.instance_id:
            live_summary = ready_summary = 'identity_mismatch'
        elif age < -30:
            live_summary = ready_summary = 'snapshot_from_future'
        elif age > policy.max_age_seconds:
            live, ready = 2, 3
            live_summary = ready_summary = 'snapshot_stale'
            metric = f'heartbeat_age={int(age)}'
        else:
            metric = f'heartbeat_age={max(0, int(age))}'
            live = 0 if snapshot.alive else 2
            live_summary = 'alive_reported' if snapshot.alive else 'not_alive'
            dependencies = dict(snapshot.dependencies)
            missing = policy.required_dependencies - dependencies.keys()
            required_states = {dependencies[key] for key in policy.required_dependencies if key in dependencies}
            if not snapshot.alive:
                ready, ready_summary = 2, 'not_alive'
            elif 'failed' in required_states:
                ready, ready_summary = 2, 'required_dependency_failed'
            elif missing or 'unknown' in required_states:
                ready, ready_summary = 3, 'required_dependency_unknown'
            elif not snapshot.accepting_work:
                ready, ready_summary = 1, 'not_accepting_work'
            elif any(state != 'ok' for state in dependencies.values()):
                ready, ready_summary = 1, 'dependency_degraded'
            else:
                ready, ready_summary = 0, 'ready_reported'
            live_summary += '; version=' + snapshot.version
    prefix = f'Agent {policy.agent_id} {policy.instance_id}'
    return (f'{live} "{prefix} liveness" {metric} {live_summary}\n'
            f'{ready} "{prefix} readiness" - {ready_summary}\n')


def read_snapshot(path):
    """Bound file reads; refuse links and special files at every path component."""
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('invalid_snapshot_path')
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_directory
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT or info.st_mode & 0o007:
            raise ValueError('invalid_snapshot_file')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(LIMIT+1)
        return Snapshot.parse(raw)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True)
    parser.add_argument('--instance', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--require', action='append', default=[])
    parser.add_argument('--max-age', type=int, default=180)
    args = parser.parse_args(argv)
    try:
        policy = Policy(args.agent, args.instance, frozenset(args.require), args.max_age)
    except (ValueError, TypeError):
        print('3 "Agent collector configuration" - invalid_configuration')
        return
    try:
        snapshot = read_snapshot(args.snapshot)
    except FileNotFoundError:
        print(render(policy), end='')
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print(render(policy, unavailable='snapshot_invalid'), end='')
    else:
        print(render(policy, snapshot), end='')


if __name__ == '__main__':
    main()
