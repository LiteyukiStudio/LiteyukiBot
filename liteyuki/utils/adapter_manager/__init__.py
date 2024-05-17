from . import (
    satori,
    onebot
)


def init(config: dict):
    onebot.init()
    satori.init(config)


def register():
    onebot.register()
    satori.register()
