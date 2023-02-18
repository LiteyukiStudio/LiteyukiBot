from nonebot.plugin import PluginMetadata
from .autorun import *
from .system import *

echo = on_command(cmd="echo", permission=SUPERUSER)
liteyuki = on_command(cmd="liteyuki", permission=SUPERUSER)
download_resource = on_command(cmd="下载资源", aliases={"更新资源"}, permission=SUPERUSER)


@echo.handle()
async def _(args: Message = CommandArg()):
    await echo.send(Message(Command.escape(str(args))))


@liteyuki.handle()
async def _(bot: Bot, event: MessageEvent):
    await liteyuki.finish(f"{await get_text_by_language('7', event.user_id)}: {bot.self_id}")


@download_resource.handle()
async def _():
    pass


__plugin_meta__ = PluginMetadata(
    name="轻雪底层基础",
    description="以维持轻雪的正常运行，无法关闭",
    usage='•「liteyuki」测试Bot\n\n'
          '•「echo 消息」Bot复读，可转CQ码\n\n'
          '•「#更新/更新资源」手动更新Bot或者资源（仅私聊）\n\n'
          '•「#重启/reboot」手动重启\n\n'
          '•「#状态/state」查看状态\n\n'
          '•「#下载资源/更新资源」解决自动资源下载失败的问题\n\n'
          '•「#检查更新」检查当前版本是否为最新\n\n'
          '•「#清除缓存」在储存空间不够时再用，缓存可以加快加载效率\n\n'
          '•「#屏蔽用户/取消屏蔽 <id1> <id2>...」添加屏蔽用户，多个id空格\n\n'
          '•「#群聊启用/停用 [群号]」在当前群启用/停用Bot\n\n'
          '•「#api api_name **params」直接调用gocqAPI并获取返回结果\n\n'
          '•「#导出数据」仅私聊生效，导出liteyuki.xxx.db的数据库文件（仅私聊）\n\n'
          '•「#设置[默认]语言 <语言名/语言码>」设置默认(仅超级用户)或用户的语言\n\n'
          '•「#only <id,> <msg>」指定Bot使用命令，多个id逗号分隔\n\n'
          '•「#except <id,> <msg>」指定Bot不响应，多个id逗号分隔\n\n'
          '•「#as <id> <msg>」代表用户执行命令\n\n'
          '•「liteyuki.xxx.db」将此文件发送给Bot导入数据',
    extra={
        "liteyuki_plugin": True
    }
)
