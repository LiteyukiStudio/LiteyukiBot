from typing import Optional

import pytz
from nonebot import require

from src.utils.base.data import LiteModel, Database
from src.utils.base.data_manager import User, user_db, group_db
from src.utils.base.language import Language, change_user_lang, get_all_lang, get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md
from src.utils.message.html_tool import md_to_pic
from .const import representative_timezones_list
from src.utils import event as event_utils


require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, Arparma, Subcommand, on_alconna


profile_alc = on_alconna(
    Alconna(
        "profile",
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
    ),
    aliases={"用户信息"}
)


# json储存
class Profile(LiteModel):
    lang: str = "zh-CN"
    nickname: str = ""
    timezone: str = "Asia/Shanghai"
    location: str = ""


@profile_alc.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
    user: User = user_db.where_one(User(), "user_id = ?", event_utils.get_user_id(event),
                                   default=User(user_id=str(event_utils.get_user_id(event))))
    ulang = get_user_lang(str(event_utils.get_user_id(event)))
    if result.subcommands.get("set"):
        if result.subcommands["set"].args.get("value"):
            # 对合法性进行校验后设置
            r = set_profile(result.args["key"], result.args["value"], str(event_utils.get_user_id(event)))
            if r:
                user.profile[result.args["key"]] = result.args["value"]
                user_db.save(user)  # 数据库保存
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
                # 请问这是在做什么？
                img_bytes = await md_to_pic(menu)
                await profile_alc.finish(menu)
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

        hidden_attr = ["id", "TABLE_NAME"]
        enter_attr = ["lang", "timezone"]

        for key in sorted(profile.dict().keys()):
            if key in hidden_attr:
                continue
            val = profile.dict()[key]
            key_text = ulang.get(f"user.profile.{key}")
            btn_set = md.btn_cmd(ulang.get("user.profile.edit"), f"profile set {key}",
                                 enter=True if key in enter_attr else False)
            reply += (f"\n**{key_text}**    **{val}**\n"
                      f"\n> {ulang.get(f'user.profile.{key}.desc')}"
                      f"\n> {btn_set}  \n\n***\n")
        # 这又是在做什么
        img_bytes = await md_to_pic(reply)
        await profile_alc.finish(reply)


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
            btn_set_lang = md.btn_cmd(f"{lang_name}({lang_code})", f"profile set {key} {lang_code}")
            reply += f"\n{btn_set_lang}\n***\n"
    elif key == "timezone":
        for tz in representative_timezones_list:
            btn_set_tz = md.btn_cmd(tz, f"profile set {key} {tz}")
            reply += f"{btn_set_tz}\n***\n"
    return reply


def set_profile(key: str, value: str, user_id: str) -> bool:
    """设置属性，使用if分支对每一个合法性进行检查
    Args:
        user_id:
        key:
        value:

    Returns:
        是否成功设置，输入合法性不通过返回False

    """
    if key == "lang":
        if value in get_all_lang():
            change_user_lang(user_id, value)
            return True
    elif key == "timezone":
        if value in pytz.all_timezones:
            return True
    elif key == "nickname":
        return True
