import os
import re

import jieba
from PIL import Image
from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.typing import T_State

from extraApi.base import Session, ExConfig, Log, Balance
from extraApi.cardimage import Cardimage
from .weatherApi import *


async def handleRealTimeWeather(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    if re.search(r"\d+[日,天]天气", event.raw_message) is not None:
        state["mode"] = "multiPre"
        state["days"] = int(re.search(r"\d+[日,天]天气", event.raw_message).group(0).replace("天天气", "").replace("日天气", ""))
        args, kws = Command.formatToCommand(
            event.raw_message.replace(re.search(r"\d+[日,天]天气", event.raw_message).group(0), "").strip())
    elif re.search(r"\d+小时天气", event.raw_message) is not None:
        state["mode"] = "hourPre"
        state["hours"] = int(re.search(r"\d+小时天气", event.raw_message).group(0).replace("小时天气", ""))
        args, kws = Command.formatToCommand(
            event.raw_message.replace(re.search(r"\d+小时天气", event.raw_message).group(0), "").strip())
    else:
        state["mode"] = "now"
        args, kws = Command.formatToCommand(event.raw_message.replace("天气", "").strip())

    if "more" in kws:
        state["more"] = []
        for i, m in enumerate(kws["more"].split(",")):
            state["more"].append(m.strip())
        del kws["more"]
    else:
        state["more"] = None

    # 处理城市名
    state["params"] = await ExtraData.getData(targetType=ExtraData.User, targetId=event.user_id,
                                              key="kami.weather.params", default={})
    # 原始内容,除去变量
    state["params"].update(kws)
    argStr = Command.formatToString(*args)
    if argStr != "" or "location" in kws:
        # 用户第一次输入了地点文本
        state["city"] = argStr
    else:
        # 用户第一次没输入地点
        # 检查判断绑定数据有没有字典
        if "location" not in state["params"]:
            # 第二次输入地点文本
            await bot.send(event, message="你想查询哪里的天气呢", at_sender=True)
        else:
            state["city"] = None


async def sendRealTimeWeather(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    if state["city"] is not None:
        state["params"].update({"location": str(state["city"])})
        cityList = await getQWCityInfo(state["params"])
        if cityList["code"] != "200":
            args = jieba.lcut(str(state["city"]))
            args.reverse()
            for i, arg in enumerate(args):
                if i == 0:
                    state["params"]["location"] = arg
                else:
                    state["params"]["adm"] = arg

    cityList = await getQWCityInfo(state["params"])
    if cityList["code"] == "200":
        city = cityList["location"][0]
        # 合成图片 失败发文字
        # 城市基本信息获取

        country = city["country"]  # 国家
        name = city["name"]  # 城市名
        lon = city["lon"]  # 经度
        lat = city["lat"]  # 纬度
        adm2 = city["adm2"]  # 城市上级行政区名
        adm1 = city["adm1"]  # 一级行政区名
        tz = city["tz"]  # 时区
        city_id = city["id"]  # 城市id
        rank = city["rank"]
        typ = city["type"]
        city_description = None
        if city_id in await ExtraData.getData(targetType=ExtraData.Group, targetId=0,
                                              key="kami.weather.city_description", default={}):
            city_description = (
                await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.city_description",
                                        default={}))[city_id]

        levels = [country, adm1, adm2, name]
        cityName = "%s %s" % (adm2, name)

        unit = state["params"].get("unit", None)
        if unit == "i":
            tempUnit = "℉"
        else:
            tempUnit = "℃"

        # 天气基本信息获取
        if state["mode"] == "now":
            weatherInfo = await getQWRealTimeWeather(city, state["params"])
            if weatherInfo["code"] == "200":

                preview_message = await bot.send(event, "正在生成天气卡片，请稍等...", at_sender=True)

                updateTime = weatherInfo["updateTime"]  # API响应时间
                link = weatherInfo["fxLink"]  # 链接

                weatherData = weatherInfo["now"]  # 天气数据
                obsTime = weatherData["obsTime"]  # 观测时间

                obsDate = obsTime.split("T")[0]
                obsLocalTime = obsTime.split("T")[1].split("+")[0]

                temp = weatherData["temp"]  # 气温℃
                feelsLike = weatherData["feelsLike"]  # 体感温度℃
                icon = weatherData["icon"]  # 图标码
                text = weatherData["text"]  # 天气状况文本
                wind360 = weatherData["wind360"]  # 风向角度
                windDir = weatherData["windDir"]  # 风向
                windScale = weatherData["windScale"]  # 风力等级
                windSpeed = weatherData["windSpeed"]  # 风速km/h

                humidity = weatherData["humidity"]  # 相对湿度百分比
                precip = weatherData["precip"]  # 小时累计降水量mm
                pressure = weatherData["pressure"]  # 大气压
                vis = weatherData["vis"]  # 能见度
                cloud = weatherData["cloud"]  # 云量
                dew = weatherData["dew"]  # 露点温度

                try:
                    font_80 = os.path.join(ExConfig.resPath, state["params"].get("font1", "fonts/MiSans-Heavy.ttf"))
                    font_60 = os.path.join(ExConfig.resPath, state["params"].get("font2", "fonts/MiSans_medium.ttf"))

                    base_img = Image.open(os.path.join(ExConfig.resPath, "textures/weather/mesh3.png"))
                    weather_card: Cardimage = Cardimage(baseImg=base_img)
                    # 城市名和国家 编号
                    city_pos = await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.1), xy=(0, 0),
                                                          baseAnchor=(0.05, 0.05), textAnchor=(0, 0), content=cityName,
                                                          font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(
                        0.3, Balance.clamp((city_pos[3] - city_pos[1]) / 1.2, 0.05, 0.07)), xy=(0, 0),
                                               baseAnchor=(city_pos[2] + 0.02, city_pos[1] + 0.01), textAnchor=(0, 0),
                                               content="%s | %s" % (adm1, country),
                                               font=font_80, color=Cardimage.hex2dec("ffa4a4a4"))
                    # 城市描述
                    if city_description is not None:
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.05), xy=(0, 0),
                                                   baseAnchor=(0.95, 0.075), textAnchor=(1, 0),
                                                   content=city_description,
                                                   font=font_80, color=Cardimage.hex2dec("ffa4a4a4"))

                    # 观测时间城市编号
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.9, 0.04), xy=(0, 0),
                                               baseAnchor=(0.95, 0.95), textAnchor=(1, 1),
                                               content="%s | %s %s" % (city_id, obsDate, obsLocalTime),
                                               font=font_80, color=Cardimage.hex2dec("ffa4a4a4"))
                    # 天气 状态文本 和 图片 和 温度
                    if not os.path.exists(os.path.join(ExConfig.resPath, "textures/weather/icons/%s.png" % icon)):
                        await ExtraData.download_file("https://a.hecdn.net/img/common/icon/202106d/%s.png" % icon,
                                                      os.path.join(ExConfig.resPath,
                                                                   "textures/weather/icons/%s.png" % icon))
                    await weather_card.addImage(uvSize=(1, 1), boxSize=(0.4, 0.4), xy=(0, 0),
                                                baseAnchor=(0.5, 0.45), imgAnchor=(1, 0.5),
                                                img=Image.open(os.path.join(ExConfig.resPath,
                                                                            "textures/weather/icons/%s.png" % icon)))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.15), xy=(0, 0),
                                               baseAnchor=(0.55, 0.45), textAnchor=(0, 0.1),
                                               content=text,
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.3, 0.1), xy=(0, 0),
                                               baseAnchor=(0.55, 0.4), textAnchor=(0, 0.9),
                                               content="%s%s" % (temp, tempUnit),
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))

                    # 风向风角度 风级风速 风力图标
                    wind_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.1, 0.1), xy=(0, 0),
                                                                baseAnchor=(0.1, 0.8), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.resPath,
                                                                                            "textures/weather/风速.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(wind_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 1),
                                               content="%s | %s°" % (windDir, wind360),
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(wind_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 0),
                                               content="%sLv | %skm/h" % (windScale, windSpeed),
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))

                    # 体感和湿度
                    feel_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.12, 0.12), xy=(0, 0),
                                                                baseAnchor=(0.45, 0.8), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.resPath,
                                                                                            "textures/weather/衣服.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(feel_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 1),
                                               content="%s%s" % (feelsLike, tempUnit),
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(feel_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 0),
                                               content="%sPa" % pressure,
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))

                    # 湿度和降水
                    rain_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.12, 0.12), xy=(0, 0),
                                                                baseAnchor=(0.72, 0.8), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.resPath,
                                                                                            "textures/weather/w_湿度.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(rain_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 1),
                                               content="%smm" % precip,
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.06), xy=(0, 0),
                                               baseAnchor=(rain_icon_pos[2] + 0.01, 0.8), textAnchor=(0, 0),
                                               content=f"{humidity}%",
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))

                    # 体感湿度

                    await bot.send(event,
                                   message=MessageSegment(type="image",
                                                          data={"file": "file:///%s" % await weather_card.getPath(),}))
                    await weather_card.delete()
                    await bot.delete_msg(message_id=preview_message["message_id"])
                except BaseException as ae:
                    await Session.sendException(bot, event, state, ae)

            else:
                await bot.send(event, message="%s查询失败: %s\nhttps://dev.qweather.com/docs/resource/status-code/" % (
                    "实时天气", weatherInfo["code"]), at_sender=True)
        elif state["mode"] == "multiPre":
            weatherData = await getQWDaysWeather(city, state["days"], state["params"])
            if weatherData["code"] == "200":
                reply = "%s %s日预报:" % (cityName, state["days"])
                for day in weatherData["daily"][0:state["days"]]:
                    fxDate = day["fxDate"]
                    tempMax = day["tempMax"]
                    tempMin = day["tempMin"]
                    textDay = day["textDay"]
                    textNight = day["textNight"]
                    precip = day["precip"]
                    dayText = "\n%s\n- 温度: %s~%s%s\n- 天气: %s~%s\n- 降水: %smm" % (
                        fxDate, tempMin, tempMax, tempUnit, textDay, textNight, precip)
                    more = ""
                    if state["more"] is not None:

                        for m in state["more"]:
                            more += "\n- %s: %s" % (m, day.get(m, None))
                    reply += dayText + more
                await bot.send(event, message=reply)
            else:
                await bot.send(event, message="%s查询失败: %s\nhttps://dev.qweather.com/docs/resource/status-code/" % (
                    "%s日预报天气" % state["days"], weatherData["code"]), at_sender=True)
        elif state["mode"] == "hourPre":
            weatherData = await getQWHoursWeather(city, state["hours"], state["params"])
            if weatherData["code"] == "200":
                reply = "%s %s小时预报:" % (cityName, state["hours"])
                for hour in weatherData["hourly"][0:state["hours"]]:
                    fxTime = hour["fxTime"]
                    temp = hour["temp"]
                    text = hour["text"]
                    precip = hour["precip"]
                    dayText = """\n%s\n- 温度: %s%s\n- 天气: %s\n- 降水: %smm""" % (fxTime, temp, tempUnit, text, precip)
                    more = ""
                    if state["more"] is not None:

                        for m in state["more"]:
                            more += "\n- %s: %s" % (m, hour.get(m, None))
                    reply += dayText + more
                await bot.send(event, message=reply)
            else:
                await bot.send(event, message="%s查询失败: %s\nhttps://dev.qweather.com/docs/resource/status-code/" % (
                    "%s小时预报天气" % state["hours"], weatherData["code"]), at_sender=True)
    else:
        await bot.send(event,
                       message="地点查询失败: %s\nhttps://dev.qweather.com/docs/resource/status-code/" % cityList["code"],
                       at_sender=True)

    await Log.plugin_log("kami.weather", "用户:%s查询了%s天气，状态码是%s" % (event.user_id, event.raw_message, cityList["code"]))
