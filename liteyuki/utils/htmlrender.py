import os.path

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
        pages: dict | None = None,
        wait: int = 0,
        scale_factor: float = 2,
        **kwargs
) -> bytes:
    """
    template -> html -> image
    Args:
        wait: 等待时间，单位秒
        pages: 页面参数
        template: str: 模板文件
        templates: dict: 模板参数
        scale_factor: 缩放因子，越高越清晰
        **kwargs: page 参数
    Returns:
        图片二进制数据
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)
    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        pages=pages,
        wait=wait,
        device_scale_factor=scale_factor,
    )
