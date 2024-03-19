import nonebot
from nonebot.adapters.onebot import v11, v12
from typing_extensions import Any

from .tools import de_escape
from .typing import T_Bot


async def send_markdown(markdown: str, bot: T_Bot, message_type: str, session_id: str) -> dict[str, Any]:
    formatted_md = de_escape(markdown).replace("\n", r"\n").replace("\"", r'\\\"')
    forward_data = await bot.call_api(
        api="send_private_forward_msg",
        user_id=bot.self_id,
        messages=[
            v11.MessageSegment(
                type="node",
                data={
                    "name": "Liteyuki.OneBot",
                    "uin": bot.self_id,
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
    try:
        data = await bot.send_msg(
            message_type=message_type,
            message=[
                v11.MessageSegment(
                    type="longmsg",
                    data={
                        "id": forward_data["forward_id"]
                    }
                ),
            ],


        )
    except Exception as e:
        nonebot.logger.warning("send_markdown error, send as plane text: %s", e)
        data = await bot.send_msg(
            message_type=message_type,
            message=markdown,
            user_id=session_id if message_type == "private" else None,
            group_id=session_id if message_type == "group" else None


        )
    return data
