from .reloader import Reloader
from .config import plugin_config

if plugin_config.reboot_load_command:
    from .command import reboot_matcher