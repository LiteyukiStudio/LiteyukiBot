from git import Repo

from liteyuki.bot import (
    LiteyukiBot,
    get_bot,
    get_config,
    get_config_with_compat
)

from liteyuki.comm import (
    Channel,
    Event
)

from liteyuki.plugin import (
    load_plugin,
    load_plugins
)

from liteyuki.log import (
    init_log,
    logger
)

__all__ = [
        "LiteyukiBot",
        "get_bot",
        "get_config",
        "get_config_with_compat",
        "Channel",
        "Event",
        "load_plugin",
        "load_plugins",
        "init_log",
        "logger"
]

__version__ = f"6.3.5+g{Repo('.').head.commit.hexsha}"
