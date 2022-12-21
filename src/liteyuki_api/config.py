import os.path
import json
from pydantic import BaseConfig

class Path:
    root = os.path.abspath(os.path.join(__file__, "../../.."))
    src = os.path.join(root, "src")
    config = os.path.join(src, "config")
    data = os.path.join(src, "data")


config_data = json.load(open(os.path.join(Path.config, "config.json"), encoding="utf-8"))
