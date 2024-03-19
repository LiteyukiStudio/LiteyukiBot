import nonebot

from nonebot.adapters.onebot import v11, v12
from src.utils.config import load_from_yaml

nonebot.init(**load_from_yaml("config.yml"))

adapters = [v11.Adapter, v12.Adapter]
driver = nonebot.get_driver()
for adapter in adapters:
    driver.register_adapter(adapter)

nonebot.load_plugin("src.liteyuki_main")

if __name__ == "__main__":
    nonebot.run()
