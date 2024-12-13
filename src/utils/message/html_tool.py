import os
import aiofiles  # type: ignore
import nonebot
from nonebot import require

# require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import (  # type: ignore
    template_to_html,
    template_to_pic,
    md_to_pic
)  # type: ignore


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

    ###
    if pages is None:
        pages = {
                "viewport": {
                        "width" : 1080,
                        "height": 10
                },
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
        random_file_name = f"debug.html"
        async with aiofiles.open(
                os.path.join(template_path, random_file_name), "w", encoding="utf-8"
        ) as f:
            await f.write(raw_html)
        nonebot.logger.info("Debug HTML: %s" % f"{random_file_name}")
    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        wait=wait,

        ###
        pages=pages,
        device_scale_factor=scale_factor
        ###
    )


