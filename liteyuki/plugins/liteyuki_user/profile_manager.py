from typing import Optional

import pytz
from nonebot import require

from liteyuki.utils.data import LiteModel
from liteyuki.utils.data_manager import User, user_db
from liteyuki.utils.language import Language, get_all_lang, get_user_lang
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent
from liteyuki.utils.message import Markdown as md, send_markdown
from .const import representative_timezones_list

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, Arparma, Subcommand, on_alconna

profile_alc = on_alconna(
    Alconna(
        ["profile", "个人信息"],
        Subcommand(
            "set",
            Args["key", str]["value", str, None],
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
    user: User = user_db.first(User(), "user_id = ?", event.user_id, default=User(user_id=str(event.user_id)))
    ulang = get_user_lang(str(event.user_id))
    if result.subcommands.get("set"):
        if result.subcommands["set"].args.get("value"):
            # 对合法性进行校验后设置
            r = set_profile(result.args["key"], result.args["value"])
            if r:
                user.profile[result.args["key"]] = result.args["value"]
                user_db.upsert(user)  # 数据库保存
                await profile_alc.finish(
                    ulang.get(
                        "user.profile.set_success",
                        ATTR=ulang.get(f"user.profile.{result.args['key']}"),
                        VALUE=result.args["value"]
                    )
                )
            else:
                await profile_alc.finish(ulang.get("user.profile.set_failed", ATTR=ulang.get(f"user.profile.{result.args['key']}")))
        else:
            # 未输入值，尝试呼出菜单
            menu = get_profile_menu(result.args["key"], ulang)
            if menu:
                await send_markdown(menu, bot, event=event)
            else:
                await profile_alc.finish(ulang.get("user.profile.input_value", ATTR=ulang.get(f"user.profile.{result.args['key']}")))

        user.profile[result.args["key"]] = result.args["value"]

    elif result.subcommands.get("get"):
        if result.args["key"] in user.profile:
            await profile_alc.finish(user.profile[result.args["key"]])
        else:
            await profile_alc.finish("无此键值")
    else:
        profile = Profile(**user.profile)

        for k, v in user.profile.items():
            profile.__setattr__(k, v)

        reply = f"# {ulang.get('user.profile.info')}\n***\n"

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
                      f"\n> {ulang.get(f'user.profile.{key}.desc')}"
                      f"\n> {btn_set}  \n\n***\n")
        await send_markdown(reply, bot, event=event)


def get_profile_menu(key: str, ulang: Language) -> Optional[str]:
    """获取属性的markdown菜单
    Args:
        ulang: 用户语言
        key: 属性键

    Returns:

    """
    setting_name = ulang.get(f"user.profile.{key}")

    no_menu = ["id", "nickname", "location"]

    if key in no_menu:
        return None

    reply = f"**{setting_name} {ulang.get('user.profile.settings')}**\n***\n"
    if key == "lang":
        for lang_code, lang_name in get_all_lang().items():
            btn_set = md.button(ulang.get("user.profile.set"), f"profile set {key} {lang_code}")
            reply += f"\n{btn_set} | **{lang_name}** - {lang_code}\n***\n"
    elif key == "timezone":
        for tz in representative_timezones_list:
            btn_set_tz = md.button(tz, f"profile set {key} {tz}")
            reply += f"{btn_set_tz}\n"
    return reply


def set_profile(key: str, value: str) -> bool:
    """设置属性，使用if分支对每一个合法性进行检查
    Args:
        key:
        value:

    Returns:
        是否成功设置，输入合法性不通过返回False

    """
    if key == "lang":
        if value in get_all_lang():
            return True
    elif key == "timezone":
        if value in pytz.all_timezones:
            return True
