"""Bounded agent telemetry: instrumentation supplies facts; collectors never probe."""
import argparse
from dataclasses import dataclass
import math
import os
from pathlib import Path
import secrets

from .core import decode, encode
from .health import LIMIT, VERSION, Snapshot, name, read_snapshot

# Gauges over an explicit rolling window, not lifetime counters. Missing != zero.
# Counts are integers. Time is seconds; costs are explicitly USD.
METRICS = {
    'queue_depth': 'count', 'oldest_eligible_seconds': 'seconds',
    'running_overdue': 'count', 'reconciliation_pending': 'count',
    'execution_successes': 'count', 'execution_failures': 'count',
    'execution_timeouts': 'count', 'verified_successes': 'count',
    'verification_failures': 'count', 'peer_failures': 'count',
    'authorization_denials': 'count', 'response_median_seconds': 'seconds',
    'response_p95_seconds': 'seconds', 'handoff_p95_seconds': 'seconds',
    'queue_wait_p95_seconds': 'seconds', 'source_age_seconds': 'seconds',
    'capacity_used_percent': 'percent', 'inference_seconds': 'seconds',
    'input_tokens': 'count', 'output_tokens': 'count', 'hosted_cost_usd': 'usd',
}


@dataclass(frozen=True)
class Report:
    health: Snapshot
    window_seconds: int
    metrics: tuple[tuple[str, int | float], ...] = ()
    configuration_revision: str | None = None

    def __post_init__(self):
        if not isinstance(self.health, Snapshot):
            raise ValueError('invalid_health')
        if type(self.window_seconds) is not int or not 1 <= self.window_seconds <= 86400:
            raise ValueError('invalid_window')
        if self.configuration_revision is not None and (type(self.configuration_revision) is not str
                or not VERSION.fullmatch(self.configuration_revision)):
            raise ValueError('invalid_configuration_revision')
        metrics = tuple(tuple(item) for item in self.metrics)
        seen = set()
        for key, value in metrics:
            if key not in METRICS or key in seen or type(value) not in (int, float):
                raise ValueError('invalid_metric')
            if not 0 <= value <= 10**15 or not math.isfinite(value):
                raise ValueError('invalid_metric')
            if METRICS[key] == 'count' and type(value) is not int:
                raise ValueError('invalid_count')
            if METRICS[key] == 'percent' and value > 100:
                raise ValueError('invalid_percent')
            seen.add(key)
        values = dict(metrics)
        if ('response_median_seconds' in values and 'response_p95_seconds' in values
                and values['response_median_seconds'] > values['response_p95_seconds']):
            raise ValueError('invalid_percentiles')
        object.__setattr__(self, 'metrics', metrics)

    def as_dict(self):
        return dict(schema_version=1, health=self.health.as_dict(),
                    window_seconds=self.window_seconds, metrics=dict(self.metrics),
                    configuration_revision=self.configuration_revision)

    def to_json(self):
        raw = encode(self.as_dict())
        if len(raw.encode()) > LIMIT:
            raise ValueError('telemetry_size_limit')
        return raw

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, (str, bytes)) or len(raw if isinstance(raw, bytes) else raw.encode()) > LIMIT:
            raise ValueError('telemetry_size_limit')
        value = decode(raw)
        if (type(value) is not dict or set(value) != {'schema_version', 'health', 'window_seconds', 'metrics', 'configuration_revision'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or type(value['metrics']) is not dict):
            raise ValueError('invalid_report')
        return cls(Snapshot.parse(encode(value['health'])), value['window_seconds'],
                   tuple(value['metrics'].items()), value['configuration_revision'])


def publish(path, report):
    """Atomically replace a report in an existing service-owned, real directory.

    The caller owns the destination and approved reader group. No mkdir, chown,
    timers, freshness rewrites or automatic probes. Temporary files are mode 640.
    """
    raw = report.to_json().encode()
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('invalid_report_path')
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.telemetry-' + secrets.token_hex(16)
    fd = None
    created = False
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=directory)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
        os.fsync(directory)
    finally:
        if fd is not None:
            os.close(fd)
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


@dataclass(frozen=True)
class Target:
    agent_id: str
    instance_id: str
    path: str

    def __post_init__(self):
        name(self.agent_id); name(self.instance_id)
        if type(self.path) is not str or not Path(self.path).is_absolute() or '..' in Path(self.path).parts:
            raise ValueError('invalid_report_path')


def collect(target):
    """Always return an expected identity, even when its producer is unavailable."""
    value = dict(agent_id=target.agent_id, instance_id=target.instance_id, status='unavailable', report=None)
    try:
        report = read_snapshot(target.path, parser=Report.parse)
        if (report.health.agent_id, report.health.instance_id) != (target.agent_id, target.instance_id):
            raise ValueError('identity_mismatch')
        value.update(status='ok', report=report.as_dict())
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        value['status'] = 'invalid'
    return value


def parse_row(raw):
    """Validate one transport row on the receiving server. Never echo raw errors."""
    if len(raw.encode()) > LIMIT + 512:
        raise ValueError('row_size_limit')
    value = decode(raw)
    if type(value) is not dict or set(value) != {'agent_id', 'instance_id', 'status', 'report'}:
        raise ValueError('invalid_row')
    name(value['agent_id']); name(value['instance_id'])
    if value['status'] not in {'ok', 'unavailable', 'invalid'}:
        raise ValueError('invalid_status')
    report = None
    if value['status'] == 'ok':
        report = Report.parse(encode(value['report']))
        if (report.health.agent_id, report.health.instance_id) != (value['agent_id'], value['instance_id']):
            raise ValueError('identity_mismatch')
    elif value['report'] is not None:
        raise ValueError('invalid_row')
    return value['agent_id'] + '/' + value['instance_id'], (value['status'], report)


def export(targets):
    targets = tuple(targets)
    if len(targets) > 64 or len({(t.agent_id, t.instance_id) for t in targets}) != len(targets):
        raise ValueError('invalid_targets')
    return '<<<forge_agents:sep(0)>>>\n' + ''.join(encode(collect(target)) + '\n' for target in targets)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', nargs=3, action='append', required=True, metavar=('AGENT', 'INSTANCE', 'PATH'))
    args = parser.parse_args(argv)
    try:
        output = export(Target(*values) for values in args.target)
    except (ValueError, TypeError):
        # A stable collector service remains discoverable even for invalid config.
        output = '<<<forge_agents:sep(0)>>>\n' + encode(dict(agent_id='collector', instance_id='configuration', status='invalid', report=None)) + '\n'
    print(output, end='')


if __name__ == '__main__':
    main()
