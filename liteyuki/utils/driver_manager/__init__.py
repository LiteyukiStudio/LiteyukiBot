from .auto_set_env import auto_set_env


def init(config: dict):
    auto_set_env(config)
    return
