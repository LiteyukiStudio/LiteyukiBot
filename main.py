import nonebot
from nonebot.adapters.onebot import v11, v12
from liteyuki.utils.config import config, load_from_yaml
from liteyuki.utils import init
from liteyuki.utils.liteyuki_api import liteyuki_api

init()
nonebot.init(**load_from_yaml("config.yml"))

adapters = [v11.Adapter, v12.Adapter]
driver = nonebot.get_driver()

for adapter in adapters:
    driver.register_adapter(adapter)

nonebot.load_plugin("liteyuki.liteyuki_main")

if __name__ == "__main__":
    try:
        nonebot.run()
    except BaseException as e:
        nonebot.logger.error(f"An error occurred: {e}, Bug will be reported automatically.")
        liteyuki_api.bug_report(str(e.__repr__()))
