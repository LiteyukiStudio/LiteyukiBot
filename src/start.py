import os.path
import threading
import nonebot
import yaml
from src.api.data import Data
from nonebot import get_driver

from nonebot.adapters.onebot.v11 import Adapter as V11Adapter
from nonebot.adapters.onebot.v12 import Adapter as V12Adapter

adapters = [V11Adapter, V12Adapter]

if not os.path.exists('config.yml'):
    f = open('config.yml', 'w', encoding='utf-8')
    yaml.dump(
        {
            'liteyuki': {

            },
            'nonebot': {

            }
        },
        f,
        yaml.Dumper
    )

config = yaml.safe_load(open('config.yml', encoding='utf-8'))
if not isinstance(config, dict):
    config = dict()


class Liteyuki:
    def __init__(self, params=None):
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
        if params is None:
            params = dict()
            params.update()

        kwargs = {
            'port': 11451,
            'host': '127.0.0.1',
            'nickname': ['Liteyuki'],
            'command_start': ['']
        }
        kwargs.update(config.get('nonebot', {}))
        kwargs.update(params)

        self.running_state = 1
        nonebot.init(**kwargs)
        self.driver = get_driver()

    def start(self):
        for adapter in adapters:
            self.driver.register_adapter(adapter)
        nonebot.load_plugin('src.liteyuki_main')
        nonebot.load_plugins('src/builtin')
        nonebot.run()

        def after_load():
            nonebot.load_plugins('plugins')
            installed_plugins = Data('common', 'system').get('installed_plugins', [])
            for plugin_name in installed_plugins:
                nonebot.load_plugin(plugin_name)

        after_loader = threading.Thread(target=after_load)
        after_loader.start()

    def stop(self):
        pass

    def reboot(self):
        pass
