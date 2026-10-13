"""Synthetic Jarvis -> Bear read; no model, network, credentials or personal data."""
import json
from forge_agent_core import Agent, Grant, Principal, Reply, Request, Source, Tool


def no_arguments(arguments):
    if arguments:
        raise ValueError('unexpected_arguments')


def summary(context, arguments):
    # A real domain adapter uses context.subject_id/resource_id to scope its query.
    return Reply({'synthetic': True, 'subject': context.subject_id,
                  'summary': 'Example profile available; no actual health data'},
                 [Source('training-atlas-fixture', 'sample:profile', '2026-10-12T19:00:00Z')])


def main():
    bear = Agent('bear', [Tool('fitness.summary', no_arguments, summary)],
                 [Grant('mike', 'jarvis', 'bear', 'fitness.summary', 'mike', 'profile:summary')])
    request = Request('demo-1', 'bear', 'fitness.summary', 'mike', 'profile:summary', {})
    raw = json.dumps(request.as_dict())
    # A real peer adapter must authenticate both person and calling service.
    print(json.dumps(bear.invoke(Principal('mike', 'jarvis'), raw), indent=2))
    denied = bear.invoke(Principal('kyle', 'jarvis'), raw)
    assert denied['code'] == 'scope_denied'
    print(json.dumps(denied, indent=2))


if __name__ == '__main__':
    main()
