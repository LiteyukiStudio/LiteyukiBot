import base64
import io
from typing import Any
from urllib.parse import quote

import aiofiles
import aiohttp
import nonebot
from PIL import Image
from nonebot.adapters.onebot import v11

from .html_tool import md_to_pic
from .. import load_from_yaml
from ..base.ly_typing import T_Bot, T_Message, T_MessageEvent

config = load_from_yaml("config.yml")


async def broadcast_to_superusers(message: str | T_Message, markdown: bool = False):
    """广播消息给超级用户"""
    for bot in nonebot.get_bots().values():
        for user_id in config.get("superusers", []):
            if markdown:
                await MarkdownMessage.send_md(message, bot, message_type="private", session_id=user_id)
            else:
                await bot.send_private_msg(user_id=user_id, message=message)


class MarkdownMessage:
    @staticmethod
    async def send_md(
            markdown: str,
            bot: T_Bot, *,
            message_type: str = None,
            session_id: str | int = None
    ) -> dict[str, Any] | None:
        """
        发送Markdown消息，支持自动转为图片发送
        Args:
            markdown:
            bot:
            message_type:
            session_id:
        Returns:

        """
        plain_markdown = markdown.replace("[🔗", "[")
        md_image_bytes = await md_to_pic(
            md=plain_markdown,
            width=540,
            device_scale_factor=4
        )
        print(md_image_bytes)
        data = await bot.send_msg(
            message_type=message_type,
            group_id=session_id,
            user_id=session_id,
            message=v11.MessageSegment.image(md_image_bytes),
        )
        return data

    @staticmethod
    async def send_image(
            image: bytes | str,
            bot: T_Bot, *,
            message_type: str = None,
            session_id: str | int = None,
            event: T_MessageEvent = None,
            **kwargs
    ) -> dict:
        """
        发送单张装逼大图
        Args:
            image: 图片字节流或图片本地路径，链接请使用Markdown.image_async方法获取后通过send_md发送
            bot: bot instance
            message_type: message message_type
            session_id: session id
            event: event
            kwargs: other arguments
        Returns:
            dict: response data
        """
        if isinstance(image, str):
            async with aiofiles.open(image, "rb") as f:
                image = await f.read()
        method = 2
        if method == 2:
            base64_string = base64.b64encode(image).decode("utf-8")
            data = await bot.call_api("upload_image", file=f"base64://{base64_string}")
            await MarkdownMessage.send_md(MarkdownMessage.image(data, Image.open(io.BytesIO(image)).size), bot,
                                          message_type=message_type,
                                          session_id=session_id)

        # 其他实现端方案
        else:
            image_message_id = (await bot.send_private_msg(
                user_id=bot.self_id,
                message=[
                        v11.MessageSegment.image(file=image)
                ]
            ))["message_id"]
            image_url = (await bot.get_msg(message_id=image_message_id))["message"][0]["data"]["url"]
            image_size = Image.open(io.BytesIO(image)).size
            image_md = MarkdownMessage.image(image_url, image_size)
            return await MarkdownMessage.send_md(image_md, bot, message_type=message_type, session_id=session_id)

        if data is None:
            data = await bot.send_msg(
                message_type=message_type,
                group_id=session_id,
                user_id=session_id,
                message=v11.MessageSegment.image(image),
                **kwargs
            )
        return data

    @staticmethod
    async def get_image_url(image: bytes | str, bot: T_Bot) -> str:
        """把图片上传到图床，返回链接
        Args:
            bot: 发送的bot
            image: 图片字节流或图片本地路径
        Returns:
        """
        # 等林文轩修好Lagrange.OneBot再说

    @staticmethod
    def btn_cmd(name: str, cmd: str, reply: bool = False, enter: bool = True) -> str:
        """生成点击回调按钮
        Args:
            name: 按钮显示内容
            cmd: 发送的命令，已在函数内url编码，不需要再次编码
            reply: 是否以回复的方式发送消息
            enter: 自动发送消息则为True，否则填充到输入框

        Returns:
            markdown格式的可点击回调按钮

        """
        if "" not in config.get("command_start", ["/"]) and config.get("alconna_use_command_start", False):
            cmd = f"{config['command_start'][0]}{cmd}"
        return f"[{name}](mqqapi://aio/inlinecmd?command={quote(cmd)}&reply={str(reply).lower()}&enter={str(enter).lower()})"

    @staticmethod
    def btn_link(name: str, url: str) -> str:
        """生成点击链接按钮
        Args:
            name: 链接显示内容
            url: 链接地址

        Returns:
            markdown格式的链接

        """
        return f"[🔗{name}]({url})"

    @staticmethod
    def image(url: str, size: tuple[int, int]) -> str:
        """构建图片链接
        Args:
            size:
            url: 图片链接

        Returns:
            markdown格式的图片

        """
        return f"![image #{size[0]}px #{size[1]}px]({url})"

    @staticmethod
    async def image_async(url: str) -> str:
        """获取图片，自动请求获取大小，异步
        Args:
            url: 图片链接

        Returns:
            图片Markdown语法: ![image #{width}px #{height}px](link)

        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    image = Image.open(io.BytesIO(await resp.read()))
                    return MarkdownMessage.image(url, image.size)
        except Exception as e:
            nonebot.logger.error(f"get image error: {e}")
            return "[Image Error]"

    @staticmethod
    def escape(text: str) -> str:
        """转义特殊字符
        Args:
            text: 需要转义的文本，请勿直接把整个markdown文本传入，否则会转义掉所有字符

        Returns:
            转义后的文本

        """
        chars = "*[]()~_`>#+=|{}.!"
        for char in chars:
            text = text.replace(char, f"\\\\{char}")
        return text
