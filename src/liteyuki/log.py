"""Loguru-compatible logger retained for v6 plugins."""

from yukilog.compat import get_loguru_logger

logger = get_loguru_logger(component="legacy", runtime="v6")


def init_log(config: dict[str, object] | None = None) -> None:
    """Retained compatibility hook; sink ownership belongs to the v7 runtime."""

    logger.debug("v6 init_log() left sink configuration with the v7 runtime")


__all__ = ["init_log", "logger"]
