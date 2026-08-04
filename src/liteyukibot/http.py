"""Optional loopback-only read APIs."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Mapping
from typing import Any

type StatusProvider = Callable[[], Mapping[str, Any]]


class HttpServer:
    def __init__(self, host: str, port: int, *, status_provider: StatusProvider) -> None:
        self.host = host
        self.port = port
        self.status_provider = status_provider
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        try:
            fastapi = importlib.import_module("fastapi")
            uvicorn = importlib.import_module("uvicorn")
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "HTTP status API is enabled but not installed; run `uv add 'liteyukibot[http]'`"
            ) from error

        app = fastapi.FastAPI(title="LiteyukiBot", docs_url=None, redoc_url=None, openapi_url=None)

        async def health() -> dict[str, str]:
            return {"status": "ok"}

        async def readiness() -> dict[str, Any]:
            status = self.status_provider()
            return {"ready": status.get("state") == "ready", "state": status.get("state")}

        async def status() -> Mapping[str, Any]:
            return self.status_provider()

        async def plugins() -> Any:
            return self.status_provider().get("plugins", {})

        async def runtimes() -> Any:
            return self.status_provider().get("runtimes", {})

        app.add_api_route("/health", health, methods=["GET"])
        app.add_api_route("/ready", readiness, methods=["GET"])
        app.add_api_route("/status", status, methods=["GET"])
        app.add_api_route("/plugins", plugins, methods=["GET"])
        app.add_api_route("/runtimes", runtimes, methods=["GET"])

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            access_log=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve(), name="liteyukibot-http")
        async with asyncio.timeout(10):
            while not self._server.started:
                if self._task.done():
                    await self._task
                    raise RuntimeError("HTTP server stopped during startup")
                await asyncio.sleep(0.01)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
            self._task = None
        self._server = None


__all__ = ["HttpServer"]
