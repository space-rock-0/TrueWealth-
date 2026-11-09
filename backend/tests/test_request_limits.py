import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.core.request_limits import RequestLimitsMiddleware


def build_app():
    app = FastAPI()
    app.add_middleware(RequestLimitsMiddleware, max_bytes=64)
    @app.post('/api/statements')
    async def upload(request: Request):
        return {'size': len(await request.body())}
    return app


def test_oversized_upload_is_rejected_before_handler():
    with TestClient(build_app()) as client:
        assert client.post('/api/statements', content=b'x' * 65).status_code == 413
        assert client.post('/api/statements', content=b'x' * 12).json()['size'] == 12


def test_chunked_body_cannot_bypass_limit():
    async def run():
        async def chunks():
            yield b'x' * 40
            yield b'x' * 40
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url='http://test') as client:
            response = await client.post('/api/statements', content=chunks())
            assert response.status_code == 413
    asyncio.run(run())
