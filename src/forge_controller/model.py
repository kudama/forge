import json
import httpx


class ModelError(Exception):
    pass


class Ollama:
    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.AsyncClient(base_url=settings.model_url.rstrip('/'), timeout=settings.timeout, trust_env=False)

    async def ready(self):
        try:
            response = await self.client.get('/api/tags', timeout=3)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or 'models' not in data:
                return False
            models = data['models']
            if not isinstance(models, list):
                return False
            installed = set()
            for m in models:
                if not isinstance(m, dict) or not isinstance(m.get('name'), str):
                    return False
                installed.add(m['name'])
            required = {self.settings.model_for(agent) for agent in ('forge', 'repository_analyst', 'implementer')}
            return required.issubset(installed)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False

    async def chat(self, messages, tools, *, agent='forge'):
        payload = dict(model=self.settings.model_for(agent), messages=messages, stream=False, think=False,
                       options=dict(num_ctx=self.settings.context_length, num_predict=self.settings.max_output_tokens, temperature=0), keep_alive='5m')
        if tools:
            payload['tools'] = tools
        try:
            # Limit response size before parsing; model output is untrusted.
            async with self.client.stream('POST', '/api/chat', json=payload) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ModelError('model_response_too_large')
                data = json.loads(body)
            message = data['message']
            if not isinstance(message, dict):
                raise ModelError('invalid_model_response')
            content = message.get('content', '')
            tool_calls = message.get('tool_calls', [])
            if (not isinstance(content, str) or not isinstance(tool_calls, list)
                or (not content.strip() and not tool_calls)):
                raise ModelError('invalid_model_response')
            return message
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ModelError('model_unavailable') from None

    async def close(self):
        await self.client.aclose()
