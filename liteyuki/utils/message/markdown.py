import base64
from io import BytesIO
from urllib.parse import quote

import aiohttp
from PIL import Image

from ..base.config import get_config
from ..base.data import LiteModel
from ..base.ly_typing import T_Bot


def escape_md(text: str) -> str:
    """
    转义Markdown特殊字符
    Args:
        text: str: 文本

    Returns:
        str: 转义后文本
    """
    spacial_chars = r"\`*_{}[]()#+-.!"
    for char in spacial_chars:
        text = text.replace(char, "\\\\" + char)
    return text.replace("\n", r"\n").replace('"', r'\\\"')


def escape_decorator(func):
    def wrapper(text: str):
        return func(escape_md(text))

    return wrapper


def compile_md(comps: list[str]) -> str:
    """
    合成Markdown文本
    Args:
        comps: list[str]: 组件列表

    Returns:
        str: 编译后文本
    """
    return "".join(comps)


class MarkdownComponent:
    @staticmethod
    def heading(text: str, level: int = 1) -> str:
        """标题"""
        assert 1 <= level <= 6, "标题级别应在 1-6 之间"
        return f"{'#' * level} {text}\n"

    @staticmethod
    def bold(text: str) -> str:
        """粗体"""
        return f"**{text}**"

    @staticmethod
    def italic(text: str) -> str:
        """斜体"""
        return f"*{text}*"

    @staticmethod
    def strike(text: str) -> str:
        """删除线"""
        return f"~~{text}~~"

    @staticmethod
    def code(text: str) -> str:
        """行内代码"""
        return f"`{text}`"

    @staticmethod
    def code_block(text: str, language: str = "") -> str:
        """代码块"""
        return f"```{language}\n{text}\n```\n"

    @staticmethod
    def quote(text: str) -> str:
        """引用"""
        return f"> {text}\n\n"

    @staticmethod
    def link(text: str, url: str, symbol: bool = True) -> str:
        """
        链接

        Args:
            text: 链接文本
            url: 链接地址
            symbol: 是否显示链接图标, mqqapi请使用False
        """
        return f"[{'🔗' if symbol else ''}{text}]({url})"

    @staticmethod
    def image(url: str, *, size: tuple[int, int]) -> str:
        """
        图片，本地图片不建议直接使用
        Args:
            url: 图片链接
            size: 图片大小

        Returns:
            markdown格式的图片
        """
        return f"![image #{size[0]}px #{size[1]}px]({url})"

    @staticmethod
    async def auto_image(image: str | bytes, bot: T_Bot) -> str:
        """
        自动获取图片大小
        Args:
            image: 本地图片路径 | 图片url http/file | 图片bytes
            bot: bot对象，用于上传图片到图床

        Returns:
            markdown格式的图片
        """
        if isinstance(image, bytes):
            # 传入为二进制图片
            image_obj = Image.open(BytesIO(image))
            base64_string = base64.b64encode(image_obj.tobytes()).decode("utf-8")
            url = await bot.call_api("upload_image", file=f"base64://{base64_string}")
            size = image_obj.size
        elif isinstance(image, str):
            # 传入链接或本地路径
            if image.startswith("http"):
                # 网络请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(image) as resp:
                        image_data = await resp.read()
                url = image
                size = Image.open(BytesIO(image_data)).size

            else:
                # 本地路径/file://
                image_obj = Image.open(image.replace("file://", ""))
                base64_string = base64.b64encode(image_obj.tobytes()).decode("utf-8")
                url = await bot.call_api("upload_image", file=f"base64://{base64_string}")
                size = image_obj.size
        else:
            raise ValueError("图片类型错误")

        return MarkdownComponent.image(url, size=size)

    @staticmethod
    def table(data: list[list[any]]) -> str:
        """
        表格
        Args:
            data: 表格数据，二维列表
        Returns:
            markdown格式的表格
        """
        # 表头
        table = "|".join(map(str, data[0])) + "\n"
        table += "|".join([":-:" for _ in range(len(data[0]))]) + "\n"
        # 表内容
        for row in data[1:]:
            table += "|".join(map(str, row)) + "\n"
        return table

    @staticmethod
    def paragraph(text: str) -> str:
        """
        段落
        Args:
            text: 段落内容
        Returns:
            markdown格式的段落
        """
        return f"{text}\n"


class Mqqapi:
    @staticmethod
    @escape_decorator
    def cmd(text: str, cmd: str, enter: bool = True, reply: bool = False, use_cmd_start: bool = True) -> str:
        """
        生成点击回调文本
        Args:
            text: 显示内容
            cmd: 命令
            enter: 是否自动发送
            reply: 是否回复
            use_cmd_start: 是否使用配置的命令前缀

        Returns:
            [text](mqqapi://)   markdown格式的可点击回调文本，类似于链接
        """

        if use_cmd_start:
            command_start = get_config("command_start", [])
            if command_start:
                # 若命令前缀不为空，则使用配置的第一个命令前缀
                cmd = f"{command_start[0]}{cmd}"
        return f"[{text}](mqqapi://aio/inlinecmd?command={quote(cmd)}&reply={str(reply).lower()}&enter={str(enter).lower()})"


class RenderData(LiteModel):
    label: str
    visited_label: str
    style: int


class Button(LiteModel):
    id: int
    render_data: RenderData
