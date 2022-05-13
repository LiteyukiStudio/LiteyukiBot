import os.path
import platform
import random
from typing import Union
from .auturun import *
import aiofiles
import aiohttp
from PIL import Image
from nonebot import on_command, on_notice
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, NoticeEvent, Message
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

from extraApi.base import Balance, ExtraData, Command
from extraApi.base import ExConfig
from extraApi.cardimage import Cardimage
from extraApi.rule import pluginEnable

about = on_command(cmd="about", aliases={"关于轻雪", "关于小羽"}, rule=pluginEnable("kami.base"), priority=10, block=True)
balance = on_command(cmd="查询好感度", aliases={"查询硬币"}, rule=pluginEnable("kami.base"), priority=10, block=True)
start_close = on_command(cmd="轻雪", permission=SUPERUSER, priority=10, block=True)
echo = on_command(cmd="echo", permission=SUPERUSER, priority=10, block=True)
fileReceiver = on_notice()


@echo.handle()
async def echoHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    msg = Message(event.raw_message.split()[1].replace("&#91;", "[").replace("&#93;", "]"))
    await echo.send(message=msg)


@about.handle()
async def aboutHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    now_state = await ExtraData.get_global_data(key="enable_mode", default=1)
    text = f"""{random.choice(list(bot.config.nickname))}Bot更多信息
- 状态：{"开启" if now_state == 1 else "关闭" if now_state == 0 else "检修" if now_state == -1 else "未知"}
- 简介：小羽是一个非常可爱的开源Bot呀
- 项目：https://github.com/snowyfirefly/Liteyuki
- 运行平台：{platform.platform()}
- Python：{platform.python_version() + " " + platform.python_implementation()}
- Websocket服务端支持：Nonebot(https://v2.nonebot.dev)
- 客户端支持：go-cqhttp(https://docs.go-cqhttp.org)
    """
    await about.send(text)


@fileReceiver.handle()
async def fileReceiverHandle(bot: Bot, event: NoticeEvent, state: T_State):
    eventData = event.dict()
    if str(eventData["user_id"]) in bot.config.superusers:
        if event.notice_type == "offline_file":

            file = eventData["file"]
            name = file["name"].replace("@", "/")
            path = os.path.join(ExConfig.resPath, "file_recv", os.path.basename(name))
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

    head_icon = os.path.join(ExConfig.cachePath, "%s.png" % event.user_id)
    await ExtraData.download_file("http://q1.qlogo.cn/g?b=qq&nk=%s&s=640" % event.user_id, head_icon)

    baseImg: Image.Image = Image.open(
        os.path.join(ExConfig.resPath, "textures/base/mesh_%s.png" % random.randint(1, 3)))
    baseImg = baseImg.convert(mode="RGBA")
    themeColor = list(baseImg.getpixel((int(0.5 * baseImg.size[0]), int(baseImg.size[1] * 0.5))))
    themeColor[-1] = 128
    themeColor = tuple(themeColor)
    cardimage = Cardimage(baseImg)
    raw_head: Image.Image = Image.open(head_icon)

    user_info = await bot.get_stranger_info(user_id=event.user_id)

    font = os.path.join(ExConfig.resPath, "fonts/MiSans-medium.ttf")
    # 头像
    await cardimage.addImage(uvSize=(2, 1), boxSize=(0.3, 0.3), xy=(0, 0), baseAnchor=(0.075, 0.15), imgAnchor=(0, 0),
                             img=raw_head.convert(mode="RGBA"))
    # 昵称和qq
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.5, 0.1), xy=(0, 0), baseAnchor=(0.25, 0.2), textAnchor=(0, 0.5),
                            content=user_info["nickname"], font=font, color=Cardimage.hex2dec("ffffffff"))
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.5, 0.1), xy=(0, 0), baseAnchor=(0.25, 0.4), textAnchor=(0, 0.5),
                            content=str(event.user_id), font=font, color=Cardimage.hex2dec("ffffffff"))
    # 好感度和硬币数
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.1), xy=(0, 0), baseAnchor=(0.55, 0.2), textAnchor=(0, 0.5),
                            content="硬币：%.2f" % coin, font=font, color=Cardimage.hex2dec("ffffffff"), force_size=True)
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.1), xy=(0, 0), baseAnchor=(0.55, 0.4), textAnchor=(0, 0.5),
                            content="好感度：%.2f" % favo, font=font, color=Cardimage.hex2dec("ffffffff"), force_size=True)
    # 好感度等级
    await cardimage.addText(uvSize=(2, 1), boxSize=(0.8, 0.08), xy=(0, 0), baseAnchor=(0.075, 0.6), textAnchor=(0, 0.5),
                            content="好感度等级：%d  %s" % (
                                favoLv, ("升级还需：%.2f" % (nextLvFavo - favo)) if favo < 1000 else "已满级"), font=font,
                            color=Cardimage.hex2dec("ffffffff"), force_size=True)

    # 好感度条条
    await cardimage.addImage(uvSize=(1, 1), boxSize=(0.85, 0.1), xy=(0, 0), baseAnchor=(0.5, 0.8), imgAnchor=(0.5, 0.5),
                             img=Image.new(mode="RGBA",
                                           size=(
                                               int(cardimage.baseImg.size[0] * 0.85),
                                               int(cardimage.baseImg.size[1] * 0.1)),
                                           color=(255, 255, 255, 255)))
    await cardimage.addImage(uvSize=(1, 1), boxSize=(0.85, 0.1), xy=(0, 0), baseAnchor=(0.075, 0.8), imgAnchor=(0, 0.5),
                             img=Image.new(mode="RGBA",
                                           size=(
                                               int(cardimage.baseImg.size[0] * 0.85 * Balance.clamp(favo, 0,
                                                                                                    1000) / 1000),
                                               int(cardimage.baseImg.size[1] * 0.1)),
                                           color=themeColor))
    await balance.send(message=Message(
        "[CQ:image,file=file:///%s]" % await cardimage.getPath()))
    await cardimage.delete()


@start_close.handle()
async def start_close_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    now_state = await ExtraData.get_global_data(key="enable_mode", default=1)
    args, kw = Command.formatToCommand(event.raw_message)
    s = 1
    r = False
    if args[1] == "start":
        if now_state != 1:
            await start_close.send(message="%s开启成功" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=1)
            r = True
            s = 1
        else:
            await start_close.send(message="%s处于开启状态，无需重复操作" % list(bot.config.nickname)[0])
    elif args[1] == "close":
        if now_state != 0:
            await start_close.send(message="%s关闭成功" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=0)
            r = True
            s = 0
        else:
            await start_close.send(message="%s处于关闭状态，无需重复操作" % list(bot.config.nickname)[0])
    elif args[1] == "test":
        if now_state != -1:
            await start_close.send(message="%s已进入检修模式" % list(bot.config.nickname)[0])
            await ExtraData.set_global_data(key="enable_mode", value=-1)
            r = True
            s = -1
        else:
            await start_close.send(message="%s处于检修模式，无需重复操作" % list(bot.config.nickname)[0])
    if r:
        await Log.plugin_log("kami.base",
                             "机器人状态更新为：%s" % ("开启" if s == 1 else "关闭" if s == 0 else "检修" if s == -1 else "未知"))
