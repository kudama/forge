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
            return any(m.get('name') == self.settings.model for m in response.json()['models'])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False

    async def chat(self, messages, tools):
        payload = dict(model=self.settings.model, messages=messages, stream=False, think=False,
                       options=dict(num_ctx=4096, num_predict=512, temperature=0), keep_alive='5m')
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
            if not isinstance(message, dict) or not isinstance(message.get('content', ''), str):
                raise ModelError('invalid_model_response')
            return message
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ModelError('model_unavailable') from None

    async def close(self):
        await self.client.aclose()
