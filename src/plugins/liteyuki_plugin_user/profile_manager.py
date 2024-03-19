from nonebot import on_command
from nonebot.params import CommandArg

from src.utils.typing import T_Bot, T_Message, T_MessageEvent
from src.utils.data_manager import User, user_db
from src.utils.language import get_user_lang



attr_map = {
        "lang"    : ["lang", "language", "语言"],
        "username": ["username", "昵称", "用户名"]  # Bot称呼用户的昵称
}

attr_cmd = on_command("profile", aliases={"个人设置"}, priority=0)


@attr_cmd.handle()
async def _(bot: T_Bot, event: T_MessageEvent, args: T_Message = CommandArg()):
    user = user_db.first(User, "user_id = ?", str(event.user_id), default=User(user_id=str(event.user_id)))
    ulang = get_user_lang(str(event.user_id))

    args = str(args).split(" ", 1)
    input_key = args[0]
    attr_key = "username"
    for attr_key, attr_values in attr_map.items():
        if input_key in attr_values:
            break

    if len(args) == 1:
        # 查询
        value = user.__dict__[attr_key]
        await attr_cmd.finish(f"{ulang.get('user.profile_manager.query', ATTR=attr_key, VALUE=value)}")
    else:
        # 设置
        value = args[1]
        user.__dict__[attr_key] = value
        user_db.save(user)
        await attr_cmd.finish(f"{ulang.get('user.profile_manager.set', ATTR=attr_key, VALUE=value)}")
