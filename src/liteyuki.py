from typing import Any, Optional
import nonebot
from nonebot import DOTENV_TYPE
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v12 import Adapter as OnebotV12Adapter
from sqlalchemy import create_engine

from src.api.utils import load_config

app = None
adapters = [
        OnebotV11Adapter,
        OnebotV12Adapter
]


class Liteyuki:
    def __init__(self, *, _env_file: Optional[DOTENV_TYPE] = None, **kwargs: Any):
        print(
            '\033[34m' + r''' __        ______  ________  ________  __      __  __    __  __    __  ______ 
/  |      /      |/        |/        |/  \    /  |/  |  /  |/  |  /  |/      |
$$ |      $$$$$$/ $$$$$$$$/ $$$$$$$$/ $$  \  /$$/ $$ |  $$ |$$ | /$$/ $$$$$$/ 
$$ |        $$ |     $$ |   $$ |__     $$  \/$$/  $$ |  $$ |$$ |/$$/    $$ |  
$$ |        $$ |     $$ |   $$    |     $$  $$/   $$ |  $$ |$$  $$<     $$ |  
$$ |        $$ |     $$ |   $$$$$/       $$$$/    $$ |  $$ |$$$$$  \    $$ |  
$$ |_____  _$$ |_    $$ |   $$ |_____     $$ |    $$ \__$$ |$$ |$$  \  _$$ |_ 
$$       |/ $$   |   $$ |   $$       |    $$ |    $$    $$/ $$ | $$  |/ $$   |
$$$$$$$$/ $$$$$$/    $$/    $$$$$$$$/     $$/      $$$$$$/  $$/   $$/ $$$$$$/ ''' + '\033[0m'
        )

        kwargs = load_config()
        self.nonebot = nonebot
        self.nonebot.init(_env_file=_env_file, **kwargs)
        self.driver = self.nonebot.get_driver()

    def run(self, *args, **kwargs):
        for adapter in adapters:
            self.driver.register_adapter(adapter)
        self.nonebot.load_plugin('src.liteyuki_main')  # Load main plugin
        self.nonebot.load_plugins('src/builtin')  # Load builtin plugins
        self.nonebot.load_plugins('plugins')  # Load custom plugins
        # Todo: load from database
        self.nonebot.run(*args, **kwargs)

    def get_asgi(self):
        return self.nonebot.get_asgi()
