from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from types import MappingProxyType
from typing import Callable

MAX_BYTES = 65536
MAX_DEPTH = 32
ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('invalid_identifier')
    return value


def encode(value, depth=0):
    """Strict JSON values only; no default serializers, NaN or recursive objects."""
    if depth > MAX_DEPTH:
        raise ValueError('json_depth_limit')
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('invalid_json_key')
        for item in value.values():
            encode(item, depth+1)
    elif type(value) is list:
        for item in value:
            encode(item, depth+1)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError('invalid_json_value')
    result = json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(',', ':'))
    if len(result.encode()) > MAX_BYTES:
        raise ValueError('json_size_limit')
    return result


def decode(raw):
    if not isinstance(raw, (bytes, str)) or len(raw if isinstance(raw, bytes) else raw.encode()) > MAX_BYTES:
        raise ValueError('invalid_json_input')

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate_json_key')
            value[key] = item
        return value

    def constant(value):
        raise ValueError('invalid_json_number')

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    encode(value)
    return value


@dataclass(frozen=True)
class Principal:
    """Created by trusted authentication, never from the request/model payload."""
    principal_id: str
    caller_agent_id: str | None = None

    def __post_init__(self):
        identifier(self.principal_id)
        if self.caller_agent_id is not None:
            identifier(self.caller_agent_id)


@dataclass(frozen=True)
class Grant:
    principal_id: str
    caller_agent_id: str | None
    target_agent_id: str
    capability: str
    subject_id: str
    resource_id: str

    def __post_init__(self):
        for name in ('principal_id', 'target_agent_id', 'capability', 'subject_id', 'resource_id'):
            identifier(getattr(self, name))
        if self.caller_agent_id is not None:
            identifier(self.caller_agent_id)


@dataclass(frozen=True, init=False)
class Request:
    request_id: str
    target_agent_id: str
    capability: str
    subject_id: str
    resource_id: str
    _arguments_json: str

    def __init__(self, request_id, target_agent_id, capability, subject_id, resource_id, arguments):
        for name, value in [('request_id', request_id), ('target_agent_id', target_agent_id),
                            ('capability', capability), ('subject_id', subject_id), ('resource_id', resource_id)]:
            object.__setattr__(self, name, identifier(value))
        if type(arguments) is not dict:
            raise ValueError('invalid_arguments')
        object.__setattr__(self, '_arguments_json', encode(arguments))
        encode(self.as_dict())

    @property
    def arguments(self):
        return json.loads(self._arguments_json)

    def as_dict(self):
        return dict(schema_version=1, request_id=self.request_id, target_agent_id=self.target_agent_id,
                    capability=self.capability, subject_id=self.subject_id, resource_id=self.resource_id,
                    arguments=self.arguments)

    @classmethod
    def parse(cls, raw):
        value = decode(raw)
        fields = {'request_id', 'target_agent_id', 'capability', 'subject_id', 'resource_id', 'arguments'}
        if (type(value) is not dict or set(value) != fields | {'schema_version'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1):
            raise ValueError('invalid_request')
        return cls(**{name: value[name] for name in fields})


@dataclass(frozen=True)
class Source:
    source_id: str
    reference_id: str
    observed_at: str

    def __post_init__(self):
        identifier(self.source_id)
        identifier(self.reference_id)
        if not isinstance(self.observed_at, str):
            raise ValueError('invalid_source_time')
        stamp = datetime.fromisoformat(self.observed_at)
        if stamp.utcoffset() is None:
            raise ValueError('timezone_required')
        object.__setattr__(self, 'observed_at', stamp.astimezone(timezone.utc).isoformat())

    def as_dict(self):
        return dict(source_id=self.source_id, reference_id=self.reference_id, observed_at=self.observed_at)


@dataclass(frozen=True, init=False)
class Reply:
    _data_json: str
    sources: tuple[Source, ...]

    def __init__(self, data, sources):
        object.__setattr__(self, '_data_json', encode(data))
        sources = tuple(sources)
        if not sources or any(type(source) is not Source for source in sources):
            raise ValueError('source_required')
        object.__setattr__(self, 'sources', sources)
        encode(self.as_dict())

    @property
    def data(self):
        return json.loads(self._data_json)

    def as_dict(self):
        return dict(data=self.data, sources=[source.as_dict() for source in self.sources])


@dataclass(frozen=True)
class Context:
    principal: Principal
    request_id: str
    target_agent_id: str
    subject_id: str
    resource_id: str


@dataclass(frozen=True)
class Tool:
    name: str
    validate_arguments: Callable[[dict], None]
    handler: Callable[[Context, dict], Reply]
    effect: str = 'read'

    def __post_init__(self):
        identifier(self.name)
        if (not callable(self.validate_arguments) or not callable(self.handler)
                or self.effect not in {'read', 'write'}):
            raise ValueError('invalid_tool')


class Agent:
    """No credentials, model loop, domain store or retrying side effects."""
    def __init__(self, agent_id, tools=(), grants=()):
        self.agent_id = identifier(agent_id)
        registry = {}
        for tool in tools:
            if type(tool) is not Tool or tool.name in registry:
                raise ValueError('invalid_tool_registry')
            registry[tool.name] = tool
        self.tools = MappingProxyType(registry)
        grants = tuple(grants)
        if any(type(grant) is not Grant for grant in grants):
            raise ValueError('invalid_grants')
        self.grants = frozenset(grants)

    def invoke(self, principal, raw):
        request_id = None

        def result(status, code, reply=None):
            value = dict(schema_version=1, request_id=request_id, agent_id=self.agent_id,
                         status=status, code=code)
            if reply is not None:
                value.update(reply.as_dict())
            encode(value)
            return value

        if type(principal) is not Principal:
            return result('denied', 'unauthenticated')
        try:
            request = Request.parse(raw)
            request_id = request.request_id
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return result('failed', 'invalid_request')
        grant = Grant(principal.principal_id, principal.caller_agent_id, request.target_agent_id,
                      request.capability, request.subject_id, request.resource_id)
        if request.target_agent_id != self.agent_id or grant not in self.grants:
            return result('denied', 'scope_denied')
        tool = self.tools.get(request.capability)
        if tool is None:
            return result('failed', 'capability_unavailable')
        if tool.effect != 'read':
            return result('denied', 'action_adapter_required')
        arguments = request.arguments
        try:
            tool.validate_arguments(arguments)
        except Exception:
            return result('failed', 'invalid_arguments')
        context = Context(principal, request.request_id, self.agent_id, request.subject_id, request.resource_id)
        try:
            reply = tool.handler(context, arguments)
            if type(reply) is not Reply:
                raise ValueError('invalid_reply')
            return result('succeeded', 'read_completed', reply)
        except Exception:
            return result('failed', 'tool_failed')
