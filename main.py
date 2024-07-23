from liteyuki import LiteyukiBot
from src.utils import load_from_yaml

if __name__ in ("__main__", "__mp_main__"):
    bot = LiteyukiBot(**load_from_yaml("config.yml"))
    bot.run()
