import nonebot
from nonebot.adapters.onebot import v11, v12

from liteyuki.utils import init
from liteyuki.utils.config import load_from_yaml
from liteyuki.utils.data_manager import StoredConfig, common_db
from liteyuki.utils.ly_api import liteyuki_api

init()

store_config: dict = common_db.first(StoredConfig(), default=StoredConfig()).config

static_config = load_from_yaml("config.yml")
store_config.update(static_config)
nonebot.init(**store_config)

adapters = [v11.Adapter, v12.Adapter]
driver = nonebot.get_driver()

for adapter in adapters:
    driver.register_adapter(adapter)

nonebot.load_plugin("liteyuki.liteyuki_main")

if __name__ == "__main__":
    try:
        nonebot.run()
    except BaseException as e:
        # 排除键盘中断
        if not isinstance(e, KeyboardInterrupt):
            nonebot.logger.error(f"An error occurred: {e}, Bug will be reported automatically.")
            liteyuki_api.bug_report(str(e.__repr__()))
