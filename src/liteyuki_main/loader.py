import os

import nonebot.plugin

from src.utils.language import load_from_dir
from src.utils.resource import load_resource_from_dir

THIS_PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
RESOURCE_PATH = "src/resources"
load_resource_from_dir(RESOURCE_PATH)

nonebot.plugin.load_plugins("src/plugins")
nonebot.plugin.load_plugins("plugins")