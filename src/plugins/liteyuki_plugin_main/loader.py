import os

import nonebot.plugin

from src.utils.language import load_from_dir
from src.utils.resource import load_resource_from_dir

PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
RESOURCE_PATH = "src/resources"
load_resource_from_dir(RESOURCE_PATH)

for plugin_dir in os.listdir("src/plugins"):
    if plugin_dir != PLUGIN_NAME:
        nonebot.plugin.load_plugin(f"src.plugins.{plugin_dir}")