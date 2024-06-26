import nonebot
from src.utils import adapter_manager, driver_manager, init
from src.utils.base.config import load_from_yaml
from src.utils.base.data_manager import StoredConfig, common_db
from src.utils.base.ly_api import liteyuki_api

if __name__ == "__mp_main__":
    # Start as multiprocessing
    init()
    store_config: dict = common_db.where_one(StoredConfig(), default=StoredConfig()).config
    static_config = load_from_yaml("config.yml")
    store_config.update(static_config)
    driver_manager.init(config=store_config)
    adapter_manager.init(store_config)
    nonebot.init(**store_config)
    adapter_manager.register()
    try:
        nonebot.load_plugin("src.liteyuki_main")
        nonebot.load_from_toml("pyproject.toml")
    except BaseException as e:
        if not isinstance(e, KeyboardInterrupt):
            nonebot.logger.error(f"An error occurred: {e}, Bug will be reported automatically.")
            liteyuki_api.bug_report(str(e.__repr__()))

if __name__ == "__main__":
    # Start as __main__
    from src.utils.base.reloader import Reloader

    nonebot.run()
