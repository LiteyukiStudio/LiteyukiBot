import os.path
import platform
import random
from PIL import Image
from nonebot import on_command, on_notice
from nonebot.adapters.onebot.v11 import NoticeEvent, Message, GROUP_OWNER, GROUP_ADMIN
from nonebot.params import CommandArg
from .autorun import *
from ...extraApi.base import Balance, Command
from ...extraApi.cardimage import Cardimage
from ...extraApi.permission import MASTER
from ...extraApi.rule import check_plugin_enable
from nonebot.adapters.qqguild import GuildEvent
import psutil

PluginEnable = check_plugin_enable("kami_base")

about = on_command(cmd="/about", aliases={"/关于"}, rule=PluginEnable,
                   priority=10, block=True)
balance = on_command(cmd="查询好感度", aliases={"查询硬币", "好感度查询", "硬币查询"}, rule=PluginEnable,
                     priority=10, block=True)
balance_rank = on_command(cmd="好感度排行", rule=PluginEnable,
                          priority=10, block=True)
state = on_command(cmd="/state", aliases={"/状态"}, rule=PluginEnable, priority=10, block=True)
# 超管专区
start_close = on_command(cmd="/轻雪", permission=SUPERUSER | MASTER, priority=10, block=True, rule=PluginEnable)

echo = on_command(cmd="echo", permission=SUPERUSER | MASTER, priority=10, block=True, rule=PluginEnable)

liteyuki_auto_inner_ignored = on_command(cmd="ly-auto-ignore", priority=1, block=True)

auto_ignore = on_command(cmd="自动屏蔽", priority=1, block=True)

m = on_command(cmd="liteyuki")

fileReceiver = on_notice()


@m.handle()
async def testHandle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent, GuildEvent]):
    await m.send("轻雪机器人: %s测试成功" % bot.self_id)


@echo.handle()
async def echoHandle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    msg = Message(event.raw_message.split()[1].replace("&#91;", "[").replace("&#93;", "]"))
    await echo.send(message=msg)


@about.handle()
async def aboutHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    now_state = await ExtraData.get_global_data(key="enable_mode", default=1)
    async with aiofiles.open(os.path.join(ExConfig.res_path, "version.json"), "r", encoding="utf-8") as version_file:
        now_version_data = json.loads(await version_file.read())
        now_version = now_version_data.get("version")
        now_version_description = now_version_data.get("description")
    text = f"""Liteyuki Bot更多信息
- 昵称：{list(bot.config.nickname)[0]}
- 状态：{"开启" if now_state == 1 else "关闭" if now_state == 0 else "调试模式" if now_state == -1 else "未知"}
- 版本：{now_version}({now_version_description})
- 简介：轻雪机器人(Liteyuki Bot)是一个非常可爱的开源Bot呀，希望能和大家好好相处
- 项目：https://github.com/snowyfirefly/Liteyuki"""
    await about.send(text)


@fileReceiver.handle()
async def fileReceiverHandle(bot: Bot, event: NoticeEvent, state: T_State):
    eventData = event.dict()
    if str(eventData["user_id"]) in bot.config.superusers:
        if event.notice_type == "offline_file":

            file = eventData["file"]
            name = file["name"].replace("@", "/")
            path = os.path.join(ExConfig.res_path, "file_recv", os.path.basename(name))
            if not os.path.exists(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            url = file["url"]
            await bot.send_private_msg(user_id=eventData["user_id"], message="开始下载：%s" % url)
            async with aiohttp.ClientSession().get(url=url) as onlineFileStream:
                async with aiofiles.open(path, "wb") as fileStream:
                    await fileStream.write(await onlineFileStream.content.read())
            await bot.send_private_msg(user_id=eventData["user_id"], message="文件已下载至:%s" % path)


@balance.handle()
async def balance_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    coin = await Balance.getCoinValue(user_id=event.user_id)
    favo = await Balance.getFavoValue(user_id=event.user_id)
    favoLv, nextLvFavo = await Balance.getFavoLevel(user_id=event.user_id)

    head_icon = os.path.join(ExConfig.cache_path, "%s.png" % event.user_id)
    await ExtraData.download_file("http://q1.qlogo.cn/g?b=qq&nk=%s&s=640" % event.user_id, head_icon)

    baseImg: Image.Image = Image.open(
        os.path.join(ExConfig.res_path, "textures/base/mesh_%s.png" % random.randint(1, 3)))
    baseImg = baseImg.convert(mode="RGBA")
    themeColor = list(baseImg.getpixel((int(0.5 * baseImg.size[0]), int(baseImg.size[1] * 0.5))))
    themeColor[-1] = 128
    themeColor = tuple(themeColor)
    cardimage = Cardimage(baseImg)
    raw_head: Image.Image = Image.open(head_icon)

    user_info = await bot.get_stranger_info(user_id=event.user_id)

    font = os.path.join(ExConfig.res_path, "fonts/MiSans-medium.ttf")
    # 头像
    await cardimage.addImage(uvSize=(2, 1), boxSize=(0.3, 0.3), xyOffset=(0, 0), baseAnchor=(0.075, 0.15), imgAnchor=(0, 0),
                             img=raw_head.convert(mode="RGBA"))
    # 昵称和qq
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.5, 0.1), xyOffset=(0, 0), baseAnchor=(0.25, 0.2), textAnchor=(0, 0.5),
                            content=user_info["nickname"], font=font, color=Cardimage.hex2dec("ffffffff"))
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.5, 0.1), xyOffset=(0, 0), baseAnchor=(0.25, 0.4), textAnchor=(0, 0.5),
                            content=str(event.user_id), font=font, color=Cardimage.hex2dec("ffffffff"))
    # 好感度和硬币数
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.1), xyOffset=(0, 0), baseAnchor=(0.55, 0.2), textAnchor=(0, 0.5),
                            content="硬币：%.2f" % coin, font=font, color=Cardimage.hex2dec("ffffffff"), force_size=True)
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.1), xyOffset=(0, 0), baseAnchor=(0.55, 0.4), textAnchor=(0, 0.5),
                            content="好感度：%.2f" % favo, font=font, color=Cardimage.hex2dec("ffffffff"), force_size=True)
    # 好感度等级
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.08), xyOffset=(0, 0), baseAnchor=(0.075, 0.6), textAnchor=(0, 0.5),
                            content="好感度等级：%d  %s" % (
                                favoLv, ("升级还需：%.2f" % (nextLvFavo - favo)) if favo < 1000 else "已满级"), font=font,
                            color=Cardimage.hex2dec("ffffffff"), force_size=True)

    # 好感度条条
    await cardimage.addImage(uvSize=(1, 1), boxSize=(0.85, 0.1), xyOffset=(0, 0), baseAnchor=(0.5, 0.8), imgAnchor=(0.5, 0.5),
                             img=Image.new(mode="RGBA",
                                           size=(
                                               int(cardimage.baseImg.size[0] * 0.85),
                                               int(cardimage.baseImg.size[1] * 0.1)),
                                           color=(255, 255, 255, 255)))
    await cardimage.addImage(uvSize=(1, 1), boxSize=(0.85, 0.1), xyOffset=(0, 0), baseAnchor=(0.075, 0.8), imgAnchor=(0, 0.5),
                             img=Image.new(mode="RGBA",
                                           size=(
                                               int(cardimage.baseImg.size[0] * 0.85 * Balance.clamp(favo, 0,
                                                                                                    1000) / 1000),
                                               int(cardimage.baseImg.size[1] * 0.1)),
                                           color=themeColor))
    await balance.send(message=Message(
        "[CQ:image,file=file:///%s]" % await cardimage.getPath()))
    await cardimage.delete()


@balance_rank.handle()
async def balance_rank_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    per_message = await balance_rank.send(message="好感度排行需要遍历数据库，请耐心等待...")
    favo_list = []
    for data_base in await ExtraData.get_database_list():
        if data_base[0] == "u":
            user_id = int(data_base[1:])
            favo = await Balance.getFavoValue(user_id=user_id)
            favo_list.append((user_id, favo))

    for i in range(len(favo_list) - 1):
        for j in range(len(favo_list) - 1 - i):
            if favo_list[j][1] < favo_list[j + 1][1]:
                favo_list[j], favo_list[j + 1] = favo_list[j + 1], favo_list[j]

    reply = "好感度前20："
    rank = 0
    for user in favo_list[0:10]:
        rank += 1
        user_info = await bot.get_stranger_info(user_id=user[0])
        reply += "\n\n- %s.%s\n- %s" % (rank, user_info["nickname"], round(user[1], 2))
    await bot.delete_msg(message_id=per_message["message_id"])
    await balance_rank.send(message=reply)


@start_close.handle()
async def start_close_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State, args: Message = CommandArg()):
    now_state = await ExtraData.get_global_data(key="enable_mode", default=1)
    s = 1
    r = False
    args = str(args)
    if args in ["start", "启动", "开启"]:
        if now_state != 1:
            await start_close.send(message="%s开启成功" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=1)
            r = True
            s = 1
        else:
            await start_close.send(message="%s处于开启状态，无需重复操作" % list(bot.config.nickname)[0])
    elif args in ["close", "关闭"]:
        if now_state != 0:
            await start_close.send(message="%s关闭成功" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=0)
            r = True
            s = 0
        else:
            await start_close.send(message="%s处于关闭状态，无需重复操作" % list(bot.config.nickname)[0])
    elif args in ["debug", "调试"]:
        if now_state != -1:
            await start_close.send(message="%s已进入调试模式" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=-1)
            r = True
            s = -1
        else:
            await start_close.send(message="%s处于调试模式，无需重复操作" % list(bot.config.nickname)[0])
    if r:
        await Log.plugin_log("kami_base",
                             "机器人状态更新为：%s" % ("开启" if s == 1 else "关闭" if s == 0 else "检修" if s == -1 else "未知"))


@state.handle()
async def state_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    msg = "当前设备状态："
    each_core = psutil.cpu_percent(percpu=True)
    msg += "\nCPU:"
    for i, p in enumerate(each_core):
        try:
            msg += "\n - 核%d: %.1f" % (i + 1, p) + "%"
        except BaseException:
            pass
    msg += "\n - 平均: %.1f" % psutil.cpu_percent() + "%"
    msg += "\n内存:\n - 总计: %.1fGB\n - 已用: %.1fGB\n - 剩余: %.1fGB" % \
           (psutil.virtual_memory().total / 1024 ** 3, psutil.virtual_memory().used / 1024 ** 3, psutil.virtual_memory().free / 1024 ** 3)
    msg += "\n - BOT使用: %.1fMB" % (psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2)
    msg += "\n磁盘:"
    disk_total = 0
    disk_used = 0
    for disk in psutil.disk_partitions():
        try:
            use = psutil.disk_usage(disk.device)
            msg += "\n - %s: %.1f/%.1fGB" % (disk.device, use.used / 1024 ** 3, use.total / 1024 ** 3)
            disk_total += use.total
            disk_used += use.used
        except BaseException:
            pass
    msg += "\n - 总计: %.1f/%.1fGB" % (disk_used / 1024 ** 3, disk_total / 1024 ** 3)
    await state.send(msg)


@liteyuki_auto_inner_ignored.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = str(args)[1:]
    if int(user_id) == event.user_id:
        ignored_users = await ExtraData.get_global_data("ignored_users", [])
        if event.user_id not in ignored_users:
            ignored_users.append(event.user_id)
            await ExtraData.set_global_data("ignored_users", ignored_users)


@auto_ignore.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    await auto_ignore.send("ly-auto-ignore-%s" % bot.self_id)
