from typing import Optional

from arclet.alconna import Arparma
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Arparma, Option, Subcommand

from src.utils.data import LiteModel
from src.utils.typing import T_Bot, T_Message, T_MessageEvent
from src.utils.data_manager import User, user_db
from src.utils.language import get_user_lang
from src.utils.message import Markdown as md, send_markdown

profile_alc = on_alconna(
    Alconna(
        ["profile", "个人信息"],
        Subcommand(
            "set",
            Args["key", str]["value", str, Optional],
            alias=["s", "设置"],
        ),
        Subcommand(
            "get",
            Args["key", str],
            alias=["g", "查询"],
        ),
    )
)


# json储存
class Profile(LiteModel):
    lang: str = "zh-CN"
    nickname: str = ""
    timezone: str = "Asia/Shanghai"
    location: str = ""


@profile_alc.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
    user: User = user_db.first(User, "user_id = ?", event.user_id, default=User(user_id=str(event.user_id)))
    ulang = get_user_lang(str(event.user_id))
    if result.subcommands.get("set"):
        if result.subcommands["set"].args.get("value"):
            # TODO
            pass
        else:
            # 没有值尝试呼出菜单，若菜单为none则提示用户输入值再次尝试
            # TODO
            pass


        user.profile[result.args["key"]] = result.args["value"]

    elif result.subcommands.get("get"):
        if result.args["key"] in user.profile:
            await profile_alc.finish(user.profile[result.args["key"]])
        else:
            await profile_alc.finish("无此键值")
    else:
        profile = Profile(**user.profile)

        for k, v in user.profile:
            profile.__setattr__(k, v)

        reply = f"# {ulang.get("user.profile.settings")}\n***\n"

        hidden_attr = ["id"]
        enter_attr = ["lang", "timezone"]

        for key in sorted(profile.dict().keys()):
            if key in hidden_attr:
                continue
            val = profile.dict()[key]
            key_text = ulang.get(f"user.profile.{key}")
            btn_set = md.button(ulang.get("user.profile.edit"), f"profile set {key}",
                                enter=True if key in enter_attr else False)
            reply += (f"\n**{key_text}**    **{val}**\n"
                      f"\n > {btn_set}  {ulang.get(f'user.profile.{key}.desc')}\n\n***\n")
        await send_markdown(reply, bot, event=event)


def get_profile_menu(key: str) -> str:
    """获取属性的markdown菜单
    Args:
        key:

    Returns:

    """


def set_profile(key: str, value: str) -> bool:
    """设置属性，使用if分支对每一个合法性进行检查
    Args:
        key:
        value:

    Returns:
        是否成功设置，输入合法性不通过返回False

    """
