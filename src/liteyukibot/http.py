"""Optional loopback-only read APIs."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Mapping
from typing import Any

type StatusProvider = Callable[[], Mapping[str, Any]]


class HttpServer:
    """Represent the http server contract."""
    def __init__(self, host: str, port: int, *, status_provider: StatusProvider) -> None:
        """Initialize the http server.

        Args:
            host: The host value used by the operation.
            port: The port value used by the operation.
            status_provider: The status provider value used by the operation.

        Returns:
            None.
        """
        self.host = host
        self.port = port
        self.status_provider = status_provider
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the http server.

        Returns:
            None.
        """
        try:
            fastapi = importlib.import_module("fastapi")
            uvicorn = importlib.import_module("uvicorn")
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "HTTP status API is enabled but not installed; run `uv add 'liteyukibot-v7[http]'`"
            ) from error

        app = fastapi.FastAPI(title="LiteyukiBot", docs_url=None, redoc_url=None, openapi_url=None)

        async def health() -> dict[str, str]:
            """Implement the health operation for the start.

            Returns:
                The `dict[str, str]` result produced by the operation.

            Notes:
                Internal implementation detail for `HttpServer.start.health`. It performs the local state
                transition directly and is not a stable extension boundary.
            """
            return {"status": "ok"}

        async def readiness() -> dict[str, Any]:
            """Implement the readiness operation for the start.

            Returns:
                The `dict[str, Any]` result produced by the operation.

            Notes:
                Internal implementation detail for `HttpServer.start.readiness`. It delegates to
                `status_provider`, `get` while keeping intermediate state local to the owning operation.
            """
            status = self.status_provider()
            return {"ready": status.get("state") == "ready", "state": status.get("state")}

        async def status() -> Mapping[str, Any]:
            """Return the status of the start operation.

            Returns:
                The requested `Mapping[str, Any]` value.

            Notes:
                Internal implementation detail for `HttpServer.start.status`. It delegates to `status_provider`
                while keeping intermediate state local to the owning operation.
            """
            return self.status_provider()

        async def plugins() -> Any:
            """Implement the plugins operation for the start.

            Returns:
                The `Any` result produced by the operation.

            Notes:
                Internal implementation detail for `HttpServer.start.plugins`. It delegates to `get`,
                `status_provider` while keeping intermediate state local to the owning operation.
            """
            return self.status_provider().get("plugins", {})

        async def runtimes() -> Any:
            """Implement the runtimes operation for the start.

            Returns:
                The `Any` result produced by the operation.

            Notes:
                Internal implementation detail for `HttpServer.start.runtimes`. It delegates to `get`,
                `status_provider` while keeping intermediate state local to the owning operation.
            """
            return self.status_provider().get("runtime_health", {})

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
        """Stop the http server and release its owned resources.

        Returns:
            None.
        """
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
            self._task = None
        self._server = None


__all__ = ["HttpServer"]
