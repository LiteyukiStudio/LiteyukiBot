import os
import uuid
from typing import Any, Dict, Literal, Optional, Union

import jinja2
import aiofiles
import markdown

import pyppeteer.errors

# from pathlib import Path

from liteyuki.log import logger

from src.utils.base.resource import get_resource_path  # , temp_extract_root

from .control import get_new_page

TEMPLATES_PATH = get_resource_path("templates", abs_path=True)

env = jinja2.Environment(  # noqa: S701
    extensions=["jinja2.ext.loopcontrols"],
    loader=jinja2.FileSystemLoader(TEMPLATES_PATH),
    enable_async=True,
)


async def read_any(path: str | os.PathLike[str], mode_: str = "r") -> str | bytes:
    async with aiofiles.open(path, mode=mode_) as f:  # type: ignore
        return await f.read()


async def read_template(path: str) -> str:
    return await read_any(TEMPLATES_PATH / path)  # type: ignore


async def write_any(path: str | os.PathLike[str], content: str):
    async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
        await f.write(content)


async def template_to_html(
    template_path: str,
    template_name: str,
    **kwargs,
) -> str:
    """使用jinja2模板引擎通过html生成图片

    Args:
        template_path (str): 模板路径
        template_name (str): 模板名
        **kwargs: 模板内容
    Returns:
        str: html
    """

    template_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_path),
        enable_async=True,
    )
    template = template_env.get_template(template_name)

    return await template.render_async(**kwargs)


async def html_to_pic(
    html_path: str,
    html: str = "",
    wait: int = 0,
    # template_path: str = "file://{}".format(os.getcwd()),
    type_: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: Union[int, None] = None,
    viewport: Optional[Dict[str, Any]] = None,
    cookie: Optional[Dict[str, Any]] = None,
    user_agent: Optional[str] = None,
    device_scale_factor: float = 2,
) -> bytes:
    """html转图片

    Args:
        html (str): html文本，若存在 JavaScript 脚本则无效
        html_path (str, optional): HTML路径 如 "file:///path/to/template.html"
        wait (int, optional): 等待时间，单位毫秒，默认为 0.
        type (Literal["jpeg", "png"]): 图片类型，默认 png
        quality (int, optional): 图片质量 0-100 当为`png`时无效
        viewport: (Dict[str, Any], optional): viewport 参数
        cookie: (Dict[str, Any], optional): 页面 cookie
        user_agent: (str, optional): 页面 UA
        device_scale_factor: 缩放比例，类型为float，值越大越清晰(真正想让图片清晰更优先请调整此选项)
        **kwargs: 传入 page 的参数

    Returns:
        bytes: 图片, 可直接发送
    """
    # logger.debug(f"html:\n{html}")
    if "file:" not in html_path:
        raise Exception("html_path 应为 file:/// 协议之文件传递")

    # open(
    #     filename := os.path.join(
    #         template_path,
    #         str(uuid.uuid4()) + ".html",
    #     ),
    #     "w",
    # ).write(html)

    logger.info("截入浏览器运作")

    try:
        async with get_new_page(viewport, cookie, user_agent) as page:
            page.on("console", lambda msg: logger.debug(f"浏览器控制台: {msg.text}"))
            await page.goto(html_path, waitUntil="networkidle0")
            if html:
                await page.setContent(
                    html,
                )
            await page.waitFor(wait)

            logger.info("页面截屏")

            return await page.screenshot(
                fullPage=True,
                type=type_,
                quality=quality,
                scale=device_scale_factor,
                encoding="binary",
            )  # type: ignore
    except pyppeteer.errors.PyppeteerError as e:
        logger.error(f"浏览器页面获取出错: {e}")
        return await read_any(TEMPLATES_PATH / "chromium_error.png", "rb")  # type: ignore


async def template_to_pic(
    template_path: str,
    template_name: str,
    templates: Dict[Any, Any],
    pages: Optional[Dict[Any, Any]] = None,
    wait: int = 0,
    type_: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: Union[int, None] = None,
    viewport: Optional[Dict[str, Any]] = None,
    cookie: Optional[Dict[str, Any]] = None,
    user_agent: Optional[str] = None,
    device_scale_factor: float = 2,
) -> bytes:
    """使用jinja2模板引擎通过html生成图片

    Args:
        template_path (str): 模板路径
        template_name (str): 模板名
        templates (Dict[Any, Any]): 模板内参数 如: {"name": "abc"}
        pages (Optional[Dict[Any, Any]]): 网页参数（已弃用）
        wait (int, optional): 网页载入等待时间. Defaults to 0.
        type (Literal["jpeg", "png"]): 图片类型, 默认 png
        quality (int, optional): 图片质量 0-100 当为`png`时无效
        viewport: (Dict[str, Any], optional): viewport 参数
        cookie: (Dict[str, Any], optional): 页面 cookie
        user_agent: (str, optional): 页面 UA
        device_scale_factor: 缩放比例,类型为float,值越大越清晰(真正想让图片清晰更优先请调整此选项)
    Returns:
        bytes: 图片 可直接发送
    """
    if not viewport:
        viewport = {"width": 500, "height": 10}

    if pages and "viewport" in pages:
        viewport.update(pages["viewport"])

    if device_scale_factor:
        viewport["deviceScaleFactor"] = device_scale_factor

    template_env = jinja2.Environment(  # noqa: S701
        loader=jinja2.FileSystemLoader(template_path),
        enable_async=True,
    )

    logger.info(
        "template_name:{},template_path:{}".format(template_name, template_path)
    )

    template = template_env.get_template(template_name, template_path)

    await write_any(
        html_path_ := os.path.join(template_path, "{}.html".format(uuid.uuid4())),
        await template.render_async(**templates),
    )

    picture_raw = await html_to_pic(
        # html=html_content,
        html_path="file://{}".format(html_path_),
        wait=wait,
        type_=type_,
        quality=quality,
        viewport=viewport,
        cookie=cookie,
        user_agent=user_agent,
    )

    os.remove(html_path_)

    return picture_raw


async def text_to_pic(
    text: str,
    css_path: str = "",
    width: int = 500,
    type_: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: Union[int, None] = None,
    device_scale_factor: float = 2,
) -> bytes:
    """多行文本转图片

    Args:
        text (str): 纯文本, 可多行
        css_path (str, optional): css文件
        width (int, optional): 图片宽度，默认为 500
        type (Literal["jpeg", "png"]): 图片类型, 默认 png
        quality (int, optional): 图片质量 0-100 当为`png`时无效
        device_scale_factor: 缩放比例,类型为float,值越大越清晰(真正想让图片清晰更优先请调整此选项)

    Returns:
        bytes: 图片, 可直接发送
    """
    template = env.get_template("text.html")

    return await html_to_pic(
        html=await template.render_async(
            text=text,
            css=(
                await read_any(css_path)
                if css_path
                else await read_template("text.css")
            ),
        ),
        html_path=f"file://{css_path if css_path else TEMPLATES_PATH}",
        viewport={
            "width": width,
            "height": 10,
            "deviceScaleFactor": device_scale_factor,
        },
        type_=type_,
        quality=quality,
    )


async def md_to_pic(
    md: str = "",
    md_path: str = "",
    css_path: str = "",
    width: int = 500,
    type_: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: Union[int, None] = None,
    device_scale_factor: float = 2,
) -> bytes:
    """markdown 转 图片

    Args:
        md (str, optional): markdown 格式文本
        md_path (str, optional): markdown 文件路径
        css_path (str,  optional): css文件路径. Defaults to None.
        width (int, optional): 图片宽度，默认为 500
        type (Literal["jpeg", "png"]): 图片类型, 默认 png
        quality (int, optional): 图片质量 0-100 当为`png`时无效
        device_scale_factor: 缩放比例,类型为float,值越大越清晰(真正想让图片清晰更优先请调整此选项)

    Returns:
        bytes: 图片, 可直接发送
    """
    template = env.get_template("markdown.html")
    if not md:
        if md_path:
            md = await read_any(md_path)  # type: ignore
        else:
            raise Exception("必须输入 md 或 md_path")
    logger.debug(md)
    md = markdown.markdown(
        md,
        extensions=[
            "pymdownx.tasklist",
            "tables",
            "fenced_code",
            "codehilite",
            "mdx_math",
            "pymdownx.tilde",
        ],
        extension_configs={"mdx_math": {"enable_dollar_delimiter": True}},
    )

    logger.debug(md)
    extra = ""
    if "math/tex" in md:
        katex_css = await read_template("katex/katex.min.b64_fonts.css")
        katex_js = await read_template("katex/katex.min.js")
        mathtex_js = await read_template("katex/mathtex-script-type.min.js")
        extra = (
            f'<style type="text/css">{katex_css}</style>'
            f"<script defer>{katex_js}</script>"
            f"<script defer>{mathtex_js}</script>"
        )

    if css_path:
        css = await read_any(css_path)
    else:
        css = await read_template("github-markdown-light.css") + await read_template(
            "pygments-default.css",
        )

    return await html_to_pic(
        html=await template.render_async(md=md, css=css, extra=extra),
        html_path=f"file://{css_path if css_path else TEMPLATES_PATH}",
        viewport={
            "width": width,
            "height": 10,
            "deviceScaleFactor": device_scale_factor,
        },
        type_=type_,
        quality=quality,
    )
