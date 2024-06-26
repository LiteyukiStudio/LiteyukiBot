import os.path
import time
from os import getcwd

import aiofiles
import nonebot
from nonebot_plugin_htmlrender import *
from .tools import random_hex_string


async def html2image(
        html: str,
        wait: int = 0,
):
    pass


async def template2html(
        template: str,
        templates: dict,
) -> str:
    """
    Args:
        template: str: 模板文件
        **templates: dict: 模板参数
    Returns:
        HTML 正文
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)
    return await template_to_html(template_path, template_name, **templates)


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
        # 重载资源
        raw_html = await template_to_html(
            template_name=template_name,
            template_path=template_path,
            **templates,
        )
        random_file_name = f"debug-{random_hex_string(6)}.html"
        async with aiofiles.open(os.path.join(template_path, random_file_name), "w", encoding="utf-8") as f:
            await f.write(raw_html)
        nonebot.logger.info("Debug HTML: %s" % f"{random_file_name}")

    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        pages=pages,
        wait=wait,
        device_scale_factor=scale_factor,
    )


async def url2image(
        url: str,
        wait: int = 0,
        scale_factor: float = 1,
        type: str = "png",
        quality: int = 100,
        **kwargs
) -> bytes:
    """
    Args:
        quality:
        type:
        url: str: URL
        wait: int: 等待时间
        scale_factor: float: 缩放因子
        **kwargs: page 参数
    Returns:
        图片二进制数据
    """
    async with get_new_page(scale_factor) as page:
        await page.goto(url)
        await page.wait_for_timeout(wait)
        return await page.screenshot(
            full_page=True,
            type=type,
            quality=quality
        )
