"""Local terminal console for a running LiteyukiBot instance."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from .config import LoggingSettings
from .logging import Logger, log_payload
from .management import ManagementCaller, ManagementDanger, ManagementError, ManagementRegistry


async def run_local_console(
    registry: ManagementRegistry,
    stop_event: asyncio.Event,
    *,
    logger: Logger,
    logging: LoggingSettings,
    confirm_dangerous: Callable[[str], bool] | None = None,
) -> None:
    """Read administrator commands while preserving asynchronous log output."""

    caller = ManagementCaller.local_terminal()
    session: PromptSession[str] = PromptSession("ly> ")
    with patch_stdout(raw=True):
        while not stop_event.is_set():
            try:
                line = (await session.prompt_async()).strip()
            except (EOFError, KeyboardInterrupt):
                stop_event.set()
                return
            if not line:
                continue
            try:
                command, _arguments = registry.resolve(caller, line)
                if command.danger is ManagementDanger.CONFIRM:
                    if confirm_dangerous is None:
                        response = await session.prompt_async(f"Run {' '.join(command.name)}? [y/N] ")
                        approved = response.strip().casefold() in {"y", "yes"}
                    else:
                        approved = confirm_dangerous(f"Run {' '.join(command.name)}?")
                    if not approved:
                        print("cancelled")
                        continue
                command, result = await registry.execute(caller, line)
                log_payload(
                    logger,
                    logging,
                    operation="management.command",
                    payload={"command": line, "result": result.data if result.data is not None else result.text},
                )
                print(result.text)
            except ManagementError as error:
                print(f"error: {error}", file=sys.stderr)
            except Exception as error:
                logger.exception("management command failed: {}", error)
                print(f"error: {error}", file=sys.stderr)


def supports_local_console(*, docker: bool) -> bool:
    return not docker and sys.stdin.isatty() and sys.stdout.isatty()


__all__ = ["run_local_console", "supports_local_console"]
