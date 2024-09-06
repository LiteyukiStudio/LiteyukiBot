"""
启动脚本，会执行一些启动的操作，比如加载配置文件，初始化 bot 实例等。
"""
from liteyuki import LiteyukiBot
from liteyuki.config import load_config_in_default


if __name__ == "__main__":
    bot = LiteyukiBot(**load_config_in_default(no_waring=True))
    bot.run()
