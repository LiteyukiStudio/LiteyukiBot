"""Reference NoneBot plugin loaded by the Alpha12 managed-generation E2E."""

from nonebot import on_command

reference = on_command("liteyuki-reference", priority=100, block=False)


@reference.handle()
async def handle_reference_command() -> None:
    """Return a deterministic response when the reference command is invoked.

    Returns:
        None. NoneBot terminates the matcher after sending the response.
    """
    await reference.finish("LiteyukiBot v7 managed plugin generation is active.")


__all__ = ["handle_reference_command", "reference"]
