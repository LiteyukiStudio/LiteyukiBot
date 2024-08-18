import nonebot
from nonebot.adapters.onebot import v11, v12


def init():
    pass


def register():
    driver = nonebot.get_driver()
    driver.register_adapter(v11.Adapter)
    driver.register_adapter(v12.Adapter)
