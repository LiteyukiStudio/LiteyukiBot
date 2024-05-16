import nonebot
from nonebot.adapters.onebot import v11, v12
from nonebot.adapters import satori
from liteyuki.utils import init
from liteyuki.utils.base.config import load_from_yaml
from liteyuki.utils.base.data_manager import StoredConfig, common_db
from liteyuki.utils.base.ly_api import liteyuki_api

if __name__ == "__mp_main__":
    init()
    store_config: dict = common_db.where_one(StoredConfig(), default=StoredConfig()).config
    static_config = load_from_yaml("config.yml")
    store_config.update(static_config)
    nonebot.init(**store_config)

    if not store_config.get("enable_satori", False):
        adapters = [v11.Adapter, v12.Adapter]
    else:
        adapters = [v11.Adapter, v12.Adapter, satori.Adapter]
    driver = nonebot.get_driver()

    for adapter in adapters:
        driver.register_adapter(adapter)

    try:
        nonebot.load_plugin("liteyuki.liteyuki_main")
        nonebot.load_from_toml("pyproject.toml")
    except BaseException as e:
        if not isinstance(e, KeyboardInterrupt):
            nonebot.logger.error(f"An error occurred: {e}, Bug will be reported automatically.")
            liteyuki_api.bug_report(str(e.__repr__()))

if __name__ == "__main__":
    from liteyuki.utils.base.reloader import Reloader
    nonebot.run()
