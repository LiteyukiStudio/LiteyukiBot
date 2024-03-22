import nonebot
from nonebot.adapters.onebot import v11, v12
from typing_extensions import Any

from .tools import de_escape, encode_url
from .typing import T_Bot, T_MessageEvent


async def send_markdown(markdown: str, bot: T_Bot, *, message_type: str = None, session_id: str | int = None, event: T_MessageEvent = None, **kwargs) -> dict[str, Any]:
    formatted_md = de_escape(markdown).replace("\n", r"\n").replace("\"", r'\\\"')
    if event is not None and message_type is None:
        message_type = event.message_type
        session_id = event.user_id if event.message_type == "private" else event.group_id
    try:
        forward_data = await bot.call_api(
            api="send_private_forward_msg",
            user_id=bot.self_id,
            messages=[
                    v11.MessageSegment(
                        type="node",
                        data={
                                "name"   : "Liteyuki.OneBot",
                                "uin"    : bot.self_id,
                                "content": [
                                        {
                                                "type": "markdown",
                                                "data": {
                                                        "content": '{"content":"%s"}' % formatted_md
                                                }
                                        }
                                ]
                        },
                    )
            ]
        )
        data = await bot.send_msg(
            user_id=session_id,
            group_id=session_id,
            message_type=message_type,
            message=[
                    v11.MessageSegment(
                        type="longmsg",
                        data={
                                "id": forward_data["forward_id"]
                        }
                    ),
            ],
            **kwargs

        )
    except Exception as e:
        nonebot.logger.warning("send_markdown error, send as plane text: %s" % e)
        if isinstance(bot, v11.Bot):
            data = await bot.send_msg(
                message_type=message_type,
                message=markdown,
                user_id=int(session_id),
                group_id=int(session_id),
                **kwargs
            )
        elif isinstance(bot, v12.Bot):
            data = await bot.send_message(
                detail_type=message_type,
                message=v12.Message(
                    v12.MessageSegment.text(
                        text=markdown
                    )
                ),
                user_id=str(session_id),
                group_id=str(session_id),
                **kwargs
            )
        else:
            nonebot.logger.error("send_markdown: bot type not supported")
            data = {}
    return data


class Markdown:
    @staticmethod
    def button(name: str, cmd: str, reply: bool = False, enter: bool = True) -> str:
        """生成点击回调按钮
        Args:
            name: 按钮显示内容
            cmd: 发送的命令，已在函数内url编码，不需要再次编码
            reply: 是否以回复的方式发送消息
            enter: 自动发送消息则为True，否则填充到输入框

        Returns:
            markdown格式的可点击回调按钮

        """
        return f"[{name}](mqqapi://aio/inlinecmd?command={encode_url(cmd)}&reply={str(reply).lower()}&enter={str(enter).lower()})"

    @staticmethod
    def link(name: str, url: str) -> str:
        """生成点击链接按钮
        Args:
            name: 链接显示内容
            url: 链接地址

        Returns:
            markdown格式的链接

        """
        return f"[🔗{name}]({url})"

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
