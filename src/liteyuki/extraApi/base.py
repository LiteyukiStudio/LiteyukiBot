import time

import aiofiles
import json
import os
import re
import traceback

import aiohttp
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.exception import FinishedException, IgnoredException
from nonebot.typing import T_State
from typing import Tuple, List, Union


class ExConfig:
    pluginsPath = os.path.abspath(os.path.join(__file__, "../.."))
    rootPath = os.path.abspath(os.path.join(__file__, "../../../.."))
    resPath = os.path.join(rootPath, "resource")
    cachePath = os.path.join(rootPath, "cache")
    logPath = os.path.join(rootPath, "log")
    dataPath = os.path.join(rootPath, "data")

    @staticmethod
    async def init():
        pathList = [ExConfig.pluginsPath, ExConfig.resPath, ExConfig.cachePath]
        for path in pathList:
            if not os.path.exists(path):
                os.makedirs(path)


class Command:

    @staticmethod
    def get_keywords(old_dict: dict, *keys) -> dict:
        """

        :param old_dict:
        :param keys:
        :return:

        提取旧字典中设定键合成新字典
        """
        new = dict()
        for key in keys:
            new[key] = old_dict.get(key, "")
        return new

    @staticmethod
    def formatToCommand(cmd: str, sep: str = " ", kw=True) -> Tuple[tuple, dict]:
        """
        :param kw: 将有等号的词语分出
        :param sep: 分隔符,默认空格
        :param cmd: "arg1 arg2 para1=value1 para2=value2"
        :return:

        命令参数处理
        "%20"表示空格
        """
        cmdList = cmd.strip().split(sep)
        args = []
        keywords = {}
        for arg in cmdList:
            arg = arg.replace("%20", " ")
            if "=" in arg and kw:
                keywords[arg.split("=")[0]] = arg.split("=")[1]
            else:
                args.append(arg)
        return tuple(args), keywords

    @staticmethod
    def formatToString(*args, **keywords) -> str:

        """
        :param args:
        :param keywords:
        :return:
        会将空格转为%20
        """
        keywords.get("escape", True)
        s = ""
        for arg in args:
            s += arg.replace(" ", "%20") + " "
        for item in keywords.items():
            s += ("%s=%s" % (item[0], item[1])).replace(" ", "%20") + " "
        return s[:-1]

    @staticmethod
    def reExpressionChecker(reExp: str) -> bool:
        """
        正则表达式广泛检测和排错,False不合格
        :param reExp:
        :return: bool
        """
        matchWords = [
            "   ",
            "???12",
            "在吗?asas",
            "你好!?sas12",
            "我爱你12!",
            "1920.",
            "神羽wws",
            "今天天气真好asq",
            "数据库12as",
            "瓶子是小121萝莉!",
            "我爱你!121",
            "啥时候去?asa",
            "作业做完没?asas",
            "1234567890abcdef",
            "kami sama nan de",
            "abcdefghijklmnopqrstuvwxyz",
            "1212121"
        ]
        suc = 0
        try:
            for mw in matchWords:
                if re.search(reExp, mw) is not None:
                    suc += 1
            if suc / len(matchWords) > 0.75:
                return False
            else:
                return True
        except BaseException:
            return False


class ExtraData:
    """
    外部数据管理类

    全局数据: g1000
    """
    # json
    T = Union[int, float, str, bool, dict, list, None]
    databasePath = os.path.join(ExConfig.rootPath, "data")

    User = u = "u"
    Group = g = "g"
    targetTypeDict = {
        "u": "u",
        "g": "g",
        "group": "g",
        "private": "u"
    }

    @staticmethod
    async def download_file(url, path):
        async with aiohttp.ClientSession().get(url) as FileStream:
            async with aiofiles.open(path, "wb") as FileIO:
                await FileIO.write(await FileStream.content.read())

    @staticmethod
    async def getTargetCard(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, user_id=None):
        if user_id is None:
            user_id = event.user_id
        if type(event) is GroupMessageEvent:
            memberInfo = await bot.get_group_member_info(group_id=event.group_id, user_id=user_id)
            return memberInfo["card"] if memberInfo["card"] != "" else memberInfo["nickname"]
        else:
            return (await bot.get_stranger_info(user_id=user_id))["nickname"]

    @staticmethod
    def getTargetId(event: GroupMessageEvent | PrivateMessageEvent):
        """
        群聊返回群號, 私聊返回用戶QQ
        :param event:
        :return:
        """
        if type(event) is GroupMessageEvent:
            return event.group_id
        else:
            return event.user_id

    @staticmethod
    async def getData(targetType: str, targetId: int, key: str = None, default: T = None) -> T:
        """
        :param targetType: 目标类型: u, g, event.message_type
        :param targetId: 目标id
        :param key: 数据名, 不加返回所有数据
        :param default: 值不存在时的默认值
        :return: 数据值

        获取用户数据
        """

        targetType = ExtraData.targetTypeDict[targetType]
        if os.path.exists(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId))):
            async with aiofiles.open(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)),
                                     encoding='utf-8') as file:
                try:
                    data = json.loads(await file.read())
                    if key is None:
                        return data
                    else:
                        return data.get(str(key), default)
                except (json.JSONDecodeError, KeyError):
                    return default
        else:
            return default

    @staticmethod
    async def get_user_data(user_id: int, key: str = None, default: T = None) -> T:
        return await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key=key, default=default)

    @staticmethod
    async def get_group_data(group_id: int, key: str = None, default: T = None) -> T:
        return await ExtraData.getData(targetType=ExtraData.Group, targetId=group_id, key=key, default=default)

    @staticmethod
    async def get_global_data(key: str = None, default: T = None) -> T:
        return await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key=key, default=default)

    @staticmethod
    async def get_group_member_data(group_id: int, user_id: int, key: str = None, default: T = None) -> T:
        """
        储存在群聊数据中的成员数据

        :param group_id:
        :param user_id:
        :param key:
        :param default:
        :return:
        """
        members_data = await ExtraData.get_group_data(group_id=group_id, key="%s_members_data" % group_id,  default={})
        member_data = members_data.get(str(user_id), {})
        return member_data.get(key, default)

    @staticmethod
    async def setData(targetType: str, targetId: int, key: str, value: T) -> bool:
        """
        :param targetType: 目标类型: u, g
        :param targetId: 目标id
        :param key: 数据名, 不加返回所有数据
        :param value: 数据值, 默认是None
        :return: 成功结果

        设置用户数据
        """
        key = str(key)
        if type(value) not in [str, int, float, dict, list, tuple, set, bool, None]:
            await Log.plugin_log("kami.database", "%s")
            return False
        targetType = ExtraData.targetTypeDict[targetType]
        data = await ExtraData.getData(targetType, targetId, default=dict())
        data[key] = value
        try:
            async with aiofiles.open(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)),
                                     mode='w', encoding='utf-8') as file:
                jsonText = json.dumps(data, indent=4, ensure_ascii=False)
                await file.write(jsonText)
            return True
        except BaseException:
            traceback.print_exc()
            return False

    @staticmethod
    async def set_user_data(user_id: int, key: str, value: T) -> bool:
        return await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key=key, value=value)

    @staticmethod
    async def set_group_data(group_id: int, key: str, value: T) -> bool:
        return await ExtraData.setData(targetType=ExtraData.Group, targetId=group_id, key=key, value=value)

    @staticmethod
    async def set_global_data(key: str, value: T) -> bool:
        return await ExtraData.setData(targetType=ExtraData.Group, targetId=0, key=key, value=value)

    @staticmethod
    async def set_group_member_data(group_id: int, user_id: int, key: str, value: T) -> bool:
        members_data = await ExtraData.get_group_data(group_id=group_id, key="%s_members_data" % group_id,  default={})
        member_data = members_data.get(str(user_id), {})
        member_data[key] = value
        members_data[str(user_id)] = member_data
        return await ExtraData.set_group_data(group_id=group_id, key="%s_members_data" % group_id,  value=members_data)

    @staticmethod
    async def removeData(targetType: str, targetId: int, key: str) -> bool:
        """
        :param targetType: 目标类型: u, g
        :param targetId: 目标id
        :param key: 数据名,不填时默认重置数据
        :return: 成功结果

        移除数据条目

        不存在时返回False,只有成功移除返回True
        """
        targetType = ExtraData.targetTypeDict[targetType]
        data = await ExtraData.getData(targetType, targetId, dict())
        data.remove(key)
        try:
            async with aiofiles.open(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)),
                                     mode='w', encoding='utf-8') as file:
                json.dump(data, file)
            return True
        except BaseException:
            return False

    @staticmethod
    async def createDatabase(targetType: str, targetId: int, force=False, **initialData) -> bool:
        """
        :param targetType: 目标类型: u, g
        :param targetId: 目标id
        :param force: 数据库存在时是否覆盖
        :param initialData: 初始数据
        :return: 成功结果

        创建数据库
        """
        targetType = ExtraData.targetTypeDict[targetType]
        existence = os.path.exists(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)))
        if not existence or existence and force:
            async with aiofiles.open(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)),
                                     mode='w', encoding='utf-8') as file:
                json.dump(initialData, file)
            return True
        else:
            return False

    @staticmethod
    async def removeDataBase(targetType: str, targetId: int) -> bool:
        """
        :param targetType: 目标类型: u, g
        :param targetId: 目标id
        :return: 成功结果

        移出数据库文件

        不存在时返回False,只有成功移除返回True
        """
        targetType = ExtraData.targetTypeDict[targetType]
        try:
            os.remove(os.path.join(ExtraData.databasePath, "%s%s.json" % (targetType, targetId)))
        except BaseException:
            return False

    @staticmethod
    async def getDatabaseList() -> List[str]:
        """
        :return: ["u00000", "g00000"]
        """

        databaseList = list()
        for f in os.listdir(ExtraData.databasePath):
            if re.match("[g,u][0-9]+[.]json", f):
                databaseList.append(f.replace(".json", ""))

        return databaseList


class Nonebot:
    GPMessage = GroupMessageEvent | PrivateMessageEvent


class Session:

    @staticmethod
    async def log(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State, *text):
        msg = ""
        for m in text:
            msg += str(m) + " "
        await bot.send(event, message=msg)

    @staticmethod
    async def sendException(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State,
                            exception: BaseException, text: str = None):
        """
        :type state: object
        :param text: 描述文本
        :param bot:
        :param event:
        :param state:
        :param exception:
        :return:

        错误处理
        """
        print(state)
        if type(exception) not in [FinishedException, IgnoredException]:
            tracebackInfo = traceback.format_exception(exception)
            traceback.print_exception(exception)
            await bot.send(event=event, message="自动DEBUG\n%s:%s\n%s\n%s%s" % (
                event.user_id, event.message, tracebackInfo[0], exception.__repr__(),
                "\n%s" % text if text is not None else ""))
            await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="error_records", default=list())

    @staticmethod
    async def sendExceptionToSuperuser(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State,
                                       exception: BaseException, text: str = None):
        """
                :type state: object
                :param text: 描述文本
                :param bot:
                :param event:
                :param state:
                :param exception:
                :return:

                错误处理
                """
        print(state)
        if type(exception) not in [FinishedException, IgnoredException]:
            tracebackInfo = traceback.format_exception(exception)
            traceback.print_exception(exception)
            msg = message = "自动DEBUG(超级用户模式)\n%s:%s\n%s\n%s%s" % (
                event.user_id, event.message, tracebackInfo[0], exception.__repr__(),
                "\n%s" % text if text is not None else "")
            for superuser in bot.config.superusers:
                await bot.send_private_msg(user_id=int(superuser), message=msg)

    @staticmethod
    async def get_user_icon(user_id):
        """
        :param user_id: 获取用户头像
        :return:
        """


class Json:

    @staticmethod
    def formatToString(jsonObj: dict | list):
        pass


class Balance:
    """
    余额类，包括硬币，好感度
    """

    @staticmethod
    async def getFavoValue(user_id) -> float:
        """
        获取好感度
        :param user_id: 用户id
        :return: 成功
        """
        value: float = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="favorability",
                                               default=20)
        return value

    @staticmethod
    async def getFavoLevel(user_id) -> Tuple[int, int, int]:
        """
        :return: level, 下一级数量
        """
        favo = await Balance.getFavoValue(user_id)
        level_section = [0, 15, 40, 70, 100, 150, 200, 400, 700, 1000]
        lv = 0
        i = 0
        for i in level_section:
            if favo < i:
                break
            else:
                lv += 1
        if favo >= 1000:
            i = 0
        return lv, i

    @staticmethod
    async def editFavoValue(user_id: int, delta: float, reason: str = None) -> bool:
        """
        编辑好感度, 减少请一定加负号
        :param reason: 原因
        :param user_id: 用户id
        :param delta: 变化值
        :return: 成功
        """
        value = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="favorability", default=20)
        records = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="favorability_record",
                                          default=[])
        records.append({"time": list(time.localtime()), "reason": reason, "change": delta})
        value += delta
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="favorability", value=value)
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="favorability_record", value=records)
        return True

    @staticmethod
    async def getCoinValue(user_id) -> float:
        """
        获取硬币
        :param user_id: 用户id
        :return: 成功
        """
        value = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="coin", default=100)
        return value

    @staticmethod
    async def editCoinValue(user_id: int, delta: float, reason: str = None) -> bool:
        """
        编辑好感度
        :param reason: 原因
        :param user_id: 用户id
        :param delta: 变化值
        :return: 成功
        """
        value = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="coin", default=100)
        records = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="coin_record", default=[])
        records.append({"time": list(time.localtime()), "reason": reason, "change": delta})
        value += delta
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="coin", value=value)
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="coin_record", value=records)
        return True

    @staticmethod
    async def getDataValue(user_id: int) -> int:
        """
        获取数据硬币
        :param user_id: 用户id
        :return: 成功
        """
        value = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="dataCoin", default=16384)
        return value

    @staticmethod
    async def editDataValue(user_id: int, delta: float, reason: str = None) -> bool:
        """
        编辑数据硬币, 减少请一定加负号
        :param reason: 原因
        :param user_id: 用户id
        :param delta: 变化值
        :return: 成功
        """
        value = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="dataCoin", default=16384)
        records = await ExtraData.getData(targetType=ExtraData.User, targetId=user_id, key="dataCoinRecord", default=[])
        records.append({"time": list(time.localtime()), "reason": reason, "change": delta})
        value += delta
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="dataCoin", value=value)
        await ExtraData.setData(targetType=ExtraData.User, targetId=user_id, key="dataCoinRecord", value=records)
        return True

    @staticmethod
    def clamp(x, _min, _max) -> int | float:
        """
        :param x:
        :param _min:
        :param _max:
        :return:
        区间限定函数
        """
        if _min <= x <= _max:
            return x
        elif x < _min:
            return _min
        else:
            return _max


class Log:

    @staticmethod
    async def write(log: str):
        file_name = os.path.join(ExConfig.logPath, "%s-%s-%s.log" % tuple(list(time.localtime())[0:3]))
        async with aiofiles.open(file_name, mode="a", encoding="utf-8") as f:
            await f.write(("[%s-%s-%s %s:%s:%s]" % tuple(list(time.localtime())[0:6]) + log + "\n"))

    @staticmethod
    async def receive_message(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], *args):
        log = "[收到消息]:"
        if type(event) is GroupMessageEvent:
            group_info = await bot.get_group_info(group_id=event.group_id)
            member_info = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
            log += "群聊:%s(%s) 内 用户:%s(%s) 的 消息:%s" % (
                group_info["group_name"], event.group_id, member_info["card"], event.group_id, event.raw_message)
        else:
            user_info = await bot.get_stranger_info(user_id=event.user_id)
            log += "用户:%s(%s) 的 消息:%s" % (user_info["nickname"], event.user_id, event.raw_message)
        await Log.write(log)

    @staticmethod
    async def plugin_log(plugin_id: str, log: str):
        await Log.write("[%s]:%s" % (plugin_id, log))

    @staticmethod
    async def get_session_name(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]) -> str:
        if type(event) is GroupMessageEvent:
            group_info = await bot.get_group_info(group_id=event.group_id)
            session = "群聊:%s(%s) 内 用户:%s(%s)" % (
                group_info["group_name"], event.group_id, event.sender.nickname, event.user_id)
        else:
            session = "用户:%s(%s)" % (event.sender.nickname, event.user_id)
        return session
