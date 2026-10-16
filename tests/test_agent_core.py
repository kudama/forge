from dataclasses import FrozenInstanceError
import json

import pytest

from forge_agent_core import Agent, Grant, Principal, Reply, Request, Source, Tool

SOURCE = Source('training-atlas', 'synthetic:profile', '2026-10-12T12:00:00-07:00')
GRANT = Grant('mike', 'jarvis', 'bear', 'fitness.summary', 'mike', 'profile:summary')


def raw(**updates):
    value = Request('request-1', 'bear', 'fitness.summary', 'mike', 'profile:summary', {}).as_dict()
    value.update(updates)
    return json.dumps(value)


@pytest.fixture
def service():
    calls = []

    def validate(arguments):
        calls.append('validate')
        if arguments:
            raise ValueError('no arguments')

    def handle(context, arguments):
        calls.append(context)
        return Reply({'synthetic': True, 'subject': context.subject_id}, [SOURCE])

    return Agent('bear', [Tool('fitness.summary', validate, handle)], [GRANT]), calls


def test_authorized_peer_handoff_preserves_identity_subject_and_source(service):
    agent, calls = service
    result = agent.invoke(Principal('mike', 'jarvis'), raw())
    assert result['status'] == 'succeeded'
    assert result['request_id'] == 'request-1'
    assert result['data'] == {'synthetic': True, 'subject': 'mike'}
    assert result['sources'][0]['observed_at'] == '2026-10-12T19:00:00+00:00'
    assert calls[1].principal == Principal('mike', 'jarvis')
    assert calls[1].resource_id == 'profile:summary'


@pytest.mark.parametrize('principal,updates', [
    (Principal('kyle', 'jarvis'), {}),
    (Principal('mike', 'hermes'), {}),
    (Principal('mike'), {}),
    (Principal('mike', 'jarvis'), {'subject_id': 'kyle'}),
    (Principal('mike', 'jarvis'), {'resource_id': 'private:records'}),
    (Principal('mike', 'jarvis'), {'target_agent_id': 'thoth'}),
    (Principal('mike', 'jarvis'), {'capability': 'fitness.write'}),
])
def test_exact_scope_denied_before_argument_or_data_access(service, principal, updates):
    agent, calls = service
    result = agent.invoke(principal, raw(**updates))
    assert result['code'] == 'scope_denied'
    assert calls == []
    assert 'data' not in result and 'sources' not in result


def test_request_cannot_supply_identity_or_grants(service):
    agent, calls = service
    result = agent.invoke(Principal('mike', 'jarvis'), raw(principal_id='mike', grants=['all']))
    assert result['code'] == 'invalid_request' and calls == []
    assert agent.invoke({'principal_id': 'mike'}, raw())['code'] == 'unauthenticated'


@pytest.mark.parametrize('payload', [
    raw(schema_version=True), raw(schema_version=2), raw(arguments=[]),
    raw(subject_id='*'), raw(request_id='secret\nlog'),
    '{"schema_version":1,"schema_version":1}',
    raw(arguments={'value': float('nan')}), '[' * 40 + '0' + ']' * 40,
    raw(arguments={'value': 'x' * 65536}), b'\xff', None,
])
def test_invalid_requests_are_sanitized_without_handler_access(service, payload):
    agent, calls = service
    result = agent.invoke(Principal('mike', 'jarvis'), payload)
    assert result['code'] == 'invalid_request' and calls == []


def test_arguments_and_result_data_are_snapshots():
    arguments = {'nested': [1]}
    request = Request('r1', 'bear', 'read', 'mike', 'profile', arguments)
    arguments['nested'].append(2)
    request.arguments['nested'].append(3)
    assert request.arguments == {'nested': [1]}
    data = {'nested': [1]}
    reply = Reply(data, [SOURCE])
    data['nested'].append(2); reply.data['nested'].append(3)
    assert reply.data == {'nested': [1]}
    with pytest.raises(FrozenInstanceError):
        request.subject_id = 'kyle'


def test_grant_and_tool_collections_are_snapshots(service):
    original, _ = service
    grants = [GRANT]; tools = list(original.tools.values())
    agent = Agent('bear', tools, grants)
    grants.clear(); tools.clear()
    assert agent.invoke(Principal('mike', 'jarvis'), raw())['status'] == 'succeeded'
    with pytest.raises(TypeError):
        agent.tools['other'] = next(iter(original.tools.values()))


def test_generator_grants_are_not_consumed_by_validation(service):
    original, _ = service
    agent = Agent('bear', original.tools.values(), (grant for grant in [GRANT]))
    assert agent.invoke(Principal('mike', 'jarvis'), raw())['status'] == 'succeeded'


def test_write_handler_never_runs_even_with_matching_grant():
    tool = Tool('fitness.summary', lambda arguments: pytest.fail('no validator'),
                lambda context, arguments: pytest.fail('no write'), effect='write')
    result = Agent('bear', [tool], [GRANT]).invoke(Principal('mike', 'jarvis'), raw())
    assert result['code'] == 'action_adapter_required'


def test_domain_validator_rejects_arguments_without_handler(service):
    agent, calls = service
    result = agent.invoke(Principal('mike', 'jarvis'), raw(arguments={'subject_override': 'kyle'}))
    assert result['code'] == 'invalid_arguments' and calls == ['validate']


def test_validator_boolean_return_cannot_silently_accept_invalid_arguments():
    tool = Tool('fitness.summary', lambda arguments: False,
                lambda context, arguments: pytest.fail('rejected validator must not execute'))
    result = Agent('bear', [tool], [GRANT]).invoke(Principal('mike', 'jarvis'), raw())
    assert result['code'] == 'invalid_arguments'


@pytest.mark.parametrize('kind', ['exception', 'unstructured', 'too_large'])
def test_handler_failure_and_invalid_output_never_expose_content(kind):
    def handler(context, arguments):
        if kind == 'exception':
            raise RuntimeError('password=PRIVATE')
        if kind == 'unstructured':
            return {'password': 'PRIVATE'}
        return Reply({'secret': 'x' * 65536}, [SOURCE])
    agent = Agent('bear', [Tool('fitness.summary', lambda arguments: None, handler)], [GRANT])
    result = agent.invoke(Principal('mike', 'jarvis'), raw())
    assert result['code'] == 'tool_failed'
    assert 'password' not in json.dumps(result) and 'data' not in result


@pytest.mark.parametrize('stamp', ['2026-10-12', '2026-10-12T12:00:00', 'not-time', 0])
def test_provenance_requires_valid_timezone(stamp):
    with pytest.raises((ValueError, TypeError)):
        Source('provider', 'record', stamp)


def test_provenance_is_required():
    with pytest.raises(ValueError, match='source_required'):
        Reply({'synthetic': True}, [])


def test_same_capability_name_does_not_share_agents_or_grants():
    grant = Grant('mike', 'jarvis', 'thoth', 'fitness.summary', 'mike', 'profile:summary')
    thoth = Agent('thoth', [], [grant])
    result = thoth.invoke(Principal('mike', 'jarvis'), raw(target_agent_id='thoth'))
    assert result['code'] == 'capability_unavailable'


def test_all_six_peers_can_use_same_core_without_implicit_access():
    for name in ['jarvis', 'citadel', 'forge', 'thoth', 'hermes', 'bear']:
        grant = Grant('mike', None, name, 'summary', 'mike', 'synthetic:record')
        agent = Agent(name, [Tool('summary', lambda arguments: None,
            lambda context, arguments: Reply({'synthetic': True}, [SOURCE]))], [grant])
        message = json.dumps(Request('r1', name, 'summary', 'mike', 'synthetic:record', {}).as_dict())
        assert agent.invoke(Principal('mike'), message)['status'] == 'succeeded'
        assert agent.invoke(Principal('kyle'), message)['code'] == 'scope_denied'
