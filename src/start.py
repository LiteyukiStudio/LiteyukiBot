import threading
import nonebot
import yaml

config = yaml.safe_load(open('config.yml', encoding='UTF-8'))

class Liteyuki:
    def __init__(self, params=None):
        if params is None:
            params = dict()
            params.update()


        kwargs = {
            'port': 11451,
            'host': '127.0.0.1',
            'nickname': ['Liteyuki'],
        }
        kwargs.update(config.get('nonebot', {}))
        kwargs.update(params)
        self.liteyuki_main = threading.Thread(target=nonebot.run)
        self.running_state = 1
        nonebot.init(**kwargs)

    def start(self):
        self.liteyuki_main.start()
        nonebot.load_plugin('src.builtin.liteyuki_main')

    def stop(self):
        pass