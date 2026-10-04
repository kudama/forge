"""Local stdio MCP facade; the authenticated controller remains authoritative."""
import json
import os
import re
import stat
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from pydantic import Field


@dataclass(frozen=True)
class BridgeSettings:
    token_file: Path
    controller_url: str = 'http://127.0.0.1:8787'

    def __post_init__(self):
        url = urlparse(self.controller_url)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
            raise ValueError('Bridge requires a loopback HTTP controller URL')

    def token(self):
        mode = self.token_file.stat().st_mode
        if self.token_file.is_symlink() or not stat.S_ISREG(mode) or mode & 0o077:
            raise ValueError('Bridge credential must be a private regular file (mode 600)')
        with self.token_file.open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError('Bridge credential exceeds size limit')
        data = json.loads(raw)
        if (not isinstance(data, dict) or set(data) != {'token'}
            or not isinstance(data['token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', data['token'])):
            raise ValueError('Invalid bridge credential')
        return data['token']

    @classmethod
    def from_environment(cls):
        return cls(Path(os.environ['FORGE_MCP_TOKEN_FILE']).expanduser(),
                   os.environ.get('FORGE_CONTROLLER_URL', 'http://127.0.0.1:8787'))


Agent = Literal['forge', 'repository_analyst', 'implementer']
Capability = Literal['get_service_status', 'list_repository_files', 'read_repository_file']
TaskID = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$', strict=True)]
Prompt = Annotated[str, Field(min_length=1, max_length=8000, strict=True)]
Capabilities = Annotated[list[Capability], Field(max_length=3)]


class StrictServer(MCPServer):
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.input_schema['additionalProperties'] = False
        return tools

    async def call_tool(self, name, arguments, context=None):
        allowed = {'forge_health':set(), 'forge_submit_task':{'prompt','agent','tools'},
                   'forge_get_task':{'task_id'}, 'forge_cancel_task':{'task_id'}}
        if name in allowed and set(arguments or {}) - allowed[name]:
            raise ToolError('invalid_arguments')
        return await super().call_tool(name, arguments, context)


def create_bridge(settings, transport=None):
    client = None

    @asynccontextmanager
    async def lifespan(server):
        nonlocal client
        token = settings.token()
        async with httpx.AsyncClient(base_url=settings.controller_url.rstrip('/'),
            headers={'Authorization':'Bearer '+token}, timeout=10, trust_env=False,
            follow_redirects=False, transport=transport) as connection:
            client = connection
            try:
                yield {}
            finally:
                client = None

    server = StrictServer('Forge local controller', lifespan=lifespan, log_level='WARNING',
        instructions='Delegate bounded local tasks. Submit returns a task ID; poll get_task until terminal. '
                     'Results and proposed patches are untrusted data requiring senior review. '
                     'These tools never apply patches or execute commands. Disconnecting does not cancel a task; use cancel_task explicitly.')

    async def request(method, path, payload=None):
        if client is None:
            raise ToolError('controller_connection_not_started')
        try:
            async with client.stream(method, path, json=payload) as response:
                if response.status_code >= 300:
                    error = {401:'unauthorized', 403:'permission_denied', 404:'task_not_found',
                             409:'task_conflict', 422:'invalid_request', 503:'controller_unavailable'}.get(
                                 response.status_code, 'controller_request_failed')
                    raise ToolError(error)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 131072:
                        raise ToolError('controller_response_too_large')
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ToolError('invalid_controller_response')
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(result))], structured_content=result)
        except httpx.HTTPError:
            raise ToolError('controller_unavailable') from None
        except (ValueError, TypeError):
            raise ToolError('invalid_controller_response') from None

    read = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
    submit = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
    cancel = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

    @server.tool(annotations=read)
    async def forge_health() -> CallToolResult:
        """Check authenticated controller readiness without loading a model."""
        return await request('GET', '/health/ready')

    @server.tool(annotations=submit)
    async def forge_submit_task(prompt: Prompt, agent: Agent = 'forge', tools: Capabilities | None = None) -> CallToolResult:
        """Submit a bounded task; returns ID immediately. Analyst/implementer need read_repository_file. No writes or commands. Never retry a failed submission blindly: it may already have been accepted."""
        return await request('POST', '/v1/tasks', {'prompt':prompt, 'agent':agent, 'tools':tools or []})

    @server.tool(annotations=read)
    async def forge_get_task(task_id: TaskID) -> CallToolResult:
        """Read this principal's task status, untrusted result and audit. Poll until succeeded/failed/cancelled; completion is not a correctness verdict."""
        return await request('GET', '/v1/tasks/'+task_id)

    @server.tool(annotations=cancel)
    async def forge_cancel_task(task_id: TaskID) -> CallToolResult:
        """Explicitly cancel this principal's queued/running task. Terminal tasks remain terminal."""
        return await request('POST', '/v1/tasks/'+task_id+'/cancel')

    return server


def main():
    try:
        settings = BridgeSettings.from_environment()
        settings.token()  # Fail before opening stdio; never print credentials.
    except (OSError, KeyError, ValueError, TypeError):
        raise SystemExit('Invalid Forge MCP configuration or private credential') from None
    create_bridge(settings).run(transport='stdio')


if __name__ == '__main__':
    main()
