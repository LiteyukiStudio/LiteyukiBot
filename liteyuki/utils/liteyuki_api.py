import json
import os.path
import platform

import nonebot
import psutil
import requests

from . import __VERSION_I__, __VERSION__, __NAME__
from .config import config, load_from_yaml


class LiteyukiAPI:
    def __init__(self):
        self.liteyuki_id = None
        if os.path.exists("data/liteyuki/liteyuki.json"):
            with open("data/liteyuki/liteyuki.json", "rb") as f:
                self.data = json.loads(f.read())
                self.liteyuki_id = self.data.get("liteyuki_id")
        self.report = load_from_yaml("config.yml").get("auto_report", True)
        if self.report:
            nonebot.logger.info("Auto bug report is enabled")

    @property
    def device_info(self) -> dict:
        """
        获取设备信息
        Returns:

        """
        return {
                "name"        : __NAME__,
                "version"     : __VERSION__,
                "version_i"   : __VERSION_I__,
                "python"      : f"{platform.python_implementation()} {platform.python_version()}",
                "os"          : f"{platform.system()} {platform.version()} {platform.machine()}",
                "cpu"         : f"{psutil.cpu_count(logical=False)}c{psutil.cpu_count()}t{psutil.cpu_freq().current}MHz",
                "memory_total": f"{psutil.virtual_memory().total / 1024 / 1024 / 1024:.2f}GB",
                "memory_used" : f"{psutil.virtual_memory().used / 1024 / 1024 / 1024:.2f}GB",
                "memory_bot"  : f"{psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.2f}MB",
                "disk"        : f"{psutil.disk_usage('/').total / 1024 / 1024 / 1024:.2f}GB"
        }

    def bug_report(self, content: str):
        """
        提交bug报告
        Args:
            content:

        Returns:

        """
        if self.report:
            nonebot.logger.warning(f"Reporting bug...: {content}")
            url = "https://api.liteyuki.icu/bug_report"
            data = {
                    "liteyuki_id": self.liteyuki_id,
                    "content"    : content,
                    "device_info": self.device_info
            }
            resp = requests.post(url, json=data)
            if resp.status_code == 200:
                nonebot.logger.success(f"Bug report sent successfully, report_id: {resp.json().get('report_id')}")
            else:
                nonebot.logger.error(f"Bug report failed: {resp.text}")
        else:
            nonebot.logger.warning(f"Bug report is disabled: {content}")


liteyuki_api = LiteyukiAPI()
