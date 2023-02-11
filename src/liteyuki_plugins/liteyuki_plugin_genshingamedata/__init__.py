from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot import on_command, on_message

from .character_card import character_card_handle
from .player_card import bind_uid_handle, update_data_handle
from ...liteyuki_api.rule import args_end_with
from .resource import resource_git
__plugin_meta__ = PluginMetadata(
    name="原神游戏数据",
    description="查询原神游戏中的角色面板(还在开发测试，请勿使用)",
    usage="命令：\n"
          "•「绑定 <uid>」绑定自己的uid\n\n"
          "•「<角色名>面板 [uid]」查看角色面板，默认为绑定的uid，可指定uid\n\n"
          "•「更新面板 [uid]」更新角色展示框,默认为绑定的uid，可指定uid\n\n"
          "•「添加别称 <角色名> <别称1> [别称2]...」在查询面板时可以用角色别称查询\n\n"
          "•可以在「绑定uid」空格后接「lang=xx」来指定语言，可选的语言有：\n\n"
          "en ru vi th pt ko ja id fr es de zh-TW zh-CN it tr\n\n",
    extra={
        "default_enable": False,
        "liteyuki_plugin": True,
        "liteyuki_resource_git": resource_git
    }
)

bind_uid = on_command(cmd="绑定uid", aliases={"#绑定uid", "绑定", "#绑定"})
update_data = on_command(cmd="更新面板", aliases={"原神数据", "原神角色"})
add_aliases = on_command(cmd="添加别称", block=True, permission=SUPERUSER)
character_card = on_message(rule=args_end_with("面板"))


@character_card.handle()
async def _(event: MessageEvent):
    await character_card_handle(character_card, event)

@bind_uid.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    await bind_uid_handle()

@update_data.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    await update_data_handle()

@add_aliases.handle()
async def _():
    pass
