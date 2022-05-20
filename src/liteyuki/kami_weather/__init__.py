from nonebot import on_keyword, on_command
from nonebot.permission import SUPERUSER

from extraApi.rule import *
from .config import *
from .weatherHandle import *

realTimeWeather = on_keyword(keywords={"天气"}, rule=plugin_enable(pluginId="kami.weather") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT & minimumCoin(2), priority=11,
                             block=True)
bindCity = on_command(cmd="绑定天气城市", rule=plugin_enable(pluginId="kami.weather") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT, priority=10, block=True)
helpWeather = on_command(cmd="天气参数", rule=plugin_enable(pluginId="kami.weather") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT, priority=10, block=True)
setDescription = on_command(cmd="设置城市描述", rule=plugin_enable(pluginId="kami.weather") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT, permission=SUPERUSER, priority=10, block=True)
setAdvice = on_command(cmd="设置天气建议", rule=plugin_enable(pluginId="kami.weather") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT, permission=SUPERUSER, priority=10, block=True)


@setDescription.handle()
async def setDescriptionHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    try:
        args, params = Command.formatToCommand(event.raw_message)
        city_info = (await getQWCityInfo({"location": args[1]}))["location"][0]
        descriptionDict = await ExtraData.getData(targetType=ExtraData.Group, targetId=0,
                                                  key="kami.weather.city_description", default={})
        descriptionDict[city_info["id"]] = description = Command.formatToString(*args[2:]).replace("%20", " ")
        await ExtraData.setData(ExtraData.Group, targetId=0, key="kami.weather.city_description", value=descriptionDict)
        await setDescription.send(message="城市描述设置成功: %s%s%s%s %s" % (
            city_info["country"], city_info["adm1"], city_info["adm2"], city_info["name"], description))

    except BaseException as e:
        await Session.sendException(bot, event, T_State, e)


@setAdvice.handle()
async def setAdviceHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    try:
        args, params = Command.formatToCommand(event.raw_message)

        adviceDict = await ExtraData.getData(targetType=ExtraData.Group, targetId=0,
                                             key="kami.weather.advice", default={})
        advice = Command.formatToString(*args[2:]).replace("%20", " ")
        adviceDict[args[1]] = advice
        await ExtraData.setData(ExtraData.Group, targetId=0, key="kami.weather.advice", value=adviceDict)
        await setDescription.send(message="天气建议设置成功: %s-%s" % (args[1], advice))

    except BaseException as e:
        await Session.sendException(bot, event, T_State, e)


@helpWeather.handle()
async def helpWeatherHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        reply = """天气命令参数详情
lang: 语言,请参考https://dev.qweather.com/docs/resource/language/
unit: m(默认)为公制, i为英制
more: 获取更多条目, 仅支持小时和多日天气, 请参考https://dev.qweather.com/docs/api/weather/weather-daily-forecast/和https://dev.qweather.com/docs/api/weather/weather-hourly-forecast/
        """
        await helpWeather.send(message=reply)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@realTimeWeather.handle()
async def realTimeWeatherHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        await handleRealTimeWeather(bot, event, state)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@realTimeWeather.got(key="city")
async def realTimeWeatherGotCity(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        await sendRealTimeWeather(bot, event, state)
        await Balance.editCoinValue(user_id=event.user_id, delta=-2, reason="查询天气")

    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@bindCity.handle()
async def bindCityHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        args, param = Command.formatToCommand(event.raw_message)
        args = jieba.lcut(Command.formatToString(*args[1:]))
        args.reverse()
        params = {}
        for i, arg in enumerate(args):
            if i == 0:
                params["location"] = arg
            else:
                params["adm"] = arg
        params.update(param)
        cityList = await getQWCityInfo(params)
        if cityList["code"] == "200":
            params["location"] = cityList["location"][0]["id"]

            globalKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key",
                                                default="")
            if params.get("key", "") == globalKey:
                del params["key"]

            await ExtraData.setData(targetType=ExtraData.User, targetId=event.user_id, key="kami.weather.params",
                                    value=params)
            await bindCity.send(
                message="天气城市绑定成功: %s %s %s %s" % (
                    cityList["location"][0]["country"], cityList["location"][0]["adm1"],
                    cityList["location"][0]["adm2"], cityList["location"][0]["name"]),
                at_sender=True)
        else:
            await bindCity.send(message="天气城市绑定失败: %s" % cityList["code"], at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)
