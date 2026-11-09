"""Bound request bodies before JSON parsing and serialize memory-heavy uploads."""
import asyncio
import time
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException


class BodyTooLarge(HTTPException):
    def __init__(self, status_code=413):
        super().__init__(status_code, 'Upload is too large or took too long. Try a smaller file.')


class RequestLimitsMiddleware:
    def __init__(self, app, max_bytes=15 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes
        self.upload_gate = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length:
            try:
                oversized = int(length) > self.max_bytes or int(length) < 0
            except ValueError:
                oversized = True
            if oversized:
                return await JSONResponse({'detail': 'Request exceeds the 15 MB HTTP body limit.'}, status_code=413)(scope, receive, send)
        uploading = scope['method'] == 'POST' and scope['path'].rstrip('/') == '/api/statements'
        if uploading and self.upload_gate.locked():
            return await JSONResponse({'detail': 'Another statement is uploading. Wait for it to finish, then retry.'}, status_code=429)(scope, receive, send)
        total, complete, started = 0, False, False
        deadline = time.monotonic() + 60

        async def bounded_receive():
            nonlocal total, complete
            if complete:
                return await receive()
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0.01, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                raise BodyTooLarge(408) from None
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > self.max_bytes:
                    raise BodyTooLarge()
                complete = not message.get('more_body', False)
            return message

        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        async def dispatch():
            try:
                await self.app(scope, bounded_receive, tracked_send)
            except BodyTooLarge as error:
                if started:
                    raise
                await JSONResponse({'detail': error.detail}, status_code=error.status_code)(scope, receive, send)
        if uploading:
            async with self.upload_gate:
                await dispatch()
        else:
            await dispatch()
