"""Private one-request worker process for Agent sandbox Tools."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from typing import Any, cast

from liteyukibot.events.models import JsonValue

from .sandbox import run_worker_callable


async def _run(request: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Run the component operation.

    Args:
        request: Validated request object to process.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_run`. It delegates to `get`, `run_worker_callable` while
        keeping intermediate state local to the owning operation.
    """
    correlation_id = request.get("correlation_id")
    worker_ref = request.get("worker_ref")
    arguments = request.get("arguments")
    policy = request.get("policy")
    if not isinstance(correlation_id, str) or not isinstance(worker_ref, str):
        return {"correlation_id": str(correlation_id), "success": False, "error_code": "SANDBOX_PROTOCOL_INVALID"}
    if not isinstance(arguments, Mapping) or not isinstance(policy, Mapping):
        return {"correlation_id": correlation_id, "success": False, "error_code": "SANDBOX_PROTOCOL_INVALID"}
    result, error_code = await run_worker_callable(worker_ref, arguments, policy)
    response: dict[str, JsonValue] = {
        "correlation_id": correlation_id,
        "success": error_code is None,
    }
    if error_code is None:
        response["result"] = result
    else:
        response["error_code"] = error_code
    return response


def main() -> int:
    """Run the command-line entry point.

    Returns:
        The `int` result produced by the operation.
    """
    line = sys.stdin.buffer.readline()
    try:
        request = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        response: dict[str, JsonValue] = {
            "correlation_id": "",
            "success": False,
            "error_code": "SANDBOX_PROTOCOL_INVALID",
        }
    else:
        response = asyncio.run(_run(request)) if isinstance(request, Mapping) else {
            "correlation_id": "",
            "success": False,
            "error_code": "SANDBOX_PROTOCOL_INVALID",
        }
    try:
        encoded = json.dumps(cast(object, response), ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        encoded = json.dumps(
            {
                "correlation_id": response.get("correlation_id", ""),
                "success": False,
                "error_code": "SANDBOX_PROTOCOL_INVALID",
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
