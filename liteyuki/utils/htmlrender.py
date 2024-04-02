import os.path
import time
from os import getcwd

import aiofiles
from nonebot import require

require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import *


# async def html2image(
#         html: str,
#         wait: int = 0,
#         template_path: str = None,
#         scale_factor: float = 2,
#         **kwargs
# ) -> bytes:
#     """
#     Args:
#         html: str: HTML 正文
#         wait: 等待时间
#         template_path: 模板路径
#         scale_factor: 缩放因子，越高越清晰
#         **kwargs: page 参数
#
#     Returns:
#
#     """
#     return await html_to_pic(html, wait=wait, template_path=template_path, scale_factor=scale_factor)


async def template2image(
        template: str,
        templates: dict,
        pages=None,
        wait: int = 0,
        scale_factor: float = 1,
        debug: bool = False,
) -> bytes:
    """
    template -> html -> image
    Args:
        debug: 输入渲染好的 html
        wait: 等待时间，单位秒
        pages: 页面参数
        template: str: 模板文件
        templates: dict: 模板参数
        scale_factor: 缩放因子，越高越清晰
    Returns:
        图片二进制数据
    """
    if pages is None:
        pages = {
                "viewport": {
                        "width" : 1080,
                        "height": 10
                },
                "base_url": f"file://{getcwd()}",
        }
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)

    if debug:
        raw_html = await template_to_html(
            template_name=template_name,
            template_path=template_path,
            **templates,
        )
        async with aiofiles.open(os.path.join(template_path, "latest-debug.html"), "w", encoding="utf-8") as f:
            await f.write(raw_html)
        nonebot.logger.info("Debug HTML: %s" % "latest-debug.html")

    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        pages=pages,
        wait=wait,
        device_scale_factor=scale_factor,
    )
