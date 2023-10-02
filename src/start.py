import os.path
import threading
import nonebot
import yaml

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

    def reboot(self):
        pass
