"""Private Unix gateway bridge and loopback Agent Server transport."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import uvicorn

GATEWAY_SOCKET = "/run/bench-gateway/gateway.sock"
AGENT_SOCKET = "/run/bench-consumer-api/agent.sock"
ALLOWED = {("GET", "models"), ("POST", "responses"), ("POST", "responses/compact"), ("POST", "chat/completions")}


def gateway_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.rstrip("/").endswith("/v1")):
        raise ValueError("gateway_https_v1_required")
    return value.rstrip("/")


def create_app(endpoint: str, *, transport=None):
    endpoint = gateway_url(endpoint)
    slots = asyncio.Semaphore(8)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), verify=ssl.create_default_context(), trust_env=False,
                                     follow_redirects=False, transport=transport) as client:
            app.state.client = client
            yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/health/ready")
    async def health():
        return {"ready": True}

    @app.api_route("/v1/{operation:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def forward(operation: str, request: Request):
        if (request.method, operation) not in ALLOWED or request.url.query:
            return JSONResponse({"error": {"code": "route_not_allowed"}}, 403)
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) <= 7:
            return JSONResponse({"error": {"code": "gateway_credential_required"}}, 401)
        if request.method == "POST" and request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"error": {"code": "json_required"}}, 415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                return JSONResponse({"error": {"code": "request_too_large"}}, 413)
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.1)
        except TimeoutError:
            return JSONResponse({"error": {"code": "relay_capacity"}}, 429)
        response = None
        try:
            # Only the caller's restricted key is forwarded; no relay credential exists.
            upstream = app.state.client.build_request(request.method, endpoint + "/" + operation,
                content=bytes(body), headers={"Authorization": authorization, "Content-Type": "application/json",
                                             "Accept": request.headers.get("accept", "application/json")})
            response = await app.state.client.send(upstream, stream=True)
            if response.status_code != 200:
                await response.aclose()
                slots.release()
                return JSONResponse({"error": {"code": "gateway_request_failed"}}, 502)
        except (httpx.HTTPError, ValueError):
            if response is not None:
                await response.aclose()
            slots.release()
            return JSONResponse({"error": {"code": "gateway_unavailable"}}, 502)
        except BaseException:
            if response is not None:
                await response.aclose()
            slots.release()
            raise

        async def output():
            size = 0
            try:
                async with asyncio.timeout(180):
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 8_000_000:
                            return
                        yield chunk
            except (httpx.HTTPError, TimeoutError):
                return
            finally:
                await response.aclose()
                slots.release()

        return StreamingResponse(output(), media_type=response.headers.get("content-type", "application/json"),
                                 headers={"Cache-Control": "no-store"})

    return app


def health():
    with httpx.Client(transport=httpx.HTTPTransport(uds=GATEWAY_SOCKET), timeout=2, trust_env=False) as client:
        if client.get("http://localhost/health/ready").status_code != 200:
            raise RuntimeError
    with httpx.Client(timeout=2, trust_env=False) as client:
        if client.get("http://127.0.0.1:8000/health").status_code not in (200, 401, 403):
            raise RuntimeError


def main():
    if sys.argv[1:] == ["health"]:
        try:
            health()
        except Exception:
            raise SystemExit(1) from None
        return
    try:
        app = create_app(os.environ["BENCH_LITELLM_URL"])
    except (KeyError, ValueError):
        raise SystemExit("relay_configuration_invalid") from None
    # The transport process does not inherit injected application credentials.
    environment = {"PATH": os.environ["PATH"]}
    os.environ.clear()
    os.environ.update(environment)
    server = uvicorn.Server(uvicorn.Config(app, uds=GATEWAY_SOCKET, access_log=False, log_level="critical"))
    bridge = subprocess.Popen(["socat", "TCP-LISTEN:8000,bind=127.0.0.1,reuseaddr,fork,max-children=16",
                               "UNIX-CONNECT:" + AGENT_SOCKET], env=environment,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def serve():
        task = asyncio.create_task(server.serve())
        try:
            while not task.done() and bridge.poll() is None:
                await asyncio.sleep(0.2)
            server.should_exit = True
            await task
        finally:
            if bridge.poll() is None:
                bridge.terminate()
                try:
                    bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    bridge.kill()
                    bridge.wait(timeout=5)
            Path(GATEWAY_SOCKET).unlink(missing_ok=True)
        if bridge.returncode not in (0, -signal.SIGTERM):
            raise SystemExit("relay_transport_stopped")

    asyncio.run(serve())


if __name__ == "__main__":
    main()
