import json
import os.path
import platform

import aiohttp
import nonebot
import psutil
import requests
from aiohttp import FormData

from .. import __VERSION_I__, __VERSION__, __NAME__
from .config import load_from_yaml


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

    async def upload_image(self, image: bytes) -> str | None:
        """
        上传图片到图床
        Args:
            image:

        Returns:
            图片url
        """
        assert self.liteyuki_id, "Liteyuki ID is not set"
        assert isinstance(image, bytes), "Image must be bytes"
        url = "https://api.liteyuki.icu/upload_image"
        data = FormData()
        data.add_field("liteyuki_id", self.liteyuki_id)
        data.add_field('image', image, filename='image', content_type='application/octet-stream')
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    url,
                    data=data
            ) as resp:
                if resp.status == 200:
                    return (await resp.json()).get("url")
                else:
                    nonebot.logger.error(f"Upload image failed: {await resp.text()}")
                    return None


liteyuki_api = LiteyukiAPI()
