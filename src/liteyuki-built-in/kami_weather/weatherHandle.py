import os
import re

from PIL import Image
from nonebot.adapters.onebot.v11 import MessageSegment, GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.typing import T_State
from .qweather import *

from ...extraApi.base import Session, ExConfig, Log, Balance, Command
from ...extraApi.cardimage import Cardimage


async def handleRealTimeWeather(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    if re.search(r"\d+[日天]天气", event.raw_message) is not None:
        state["mode"] = "multiPre"
        state["days"] = int(re.search(r"\d+[日天]天气", event.raw_message).group(0).replace("天天气", "").replace("日天气", ""))
        args, kws = Command.formatToCommand(
            event.raw_message.replace(re.search(r"\d+[日天]天气", event.raw_message).group(0), "").strip())
    elif re.search(r"\d+小时天气", event.raw_message) is not None:
        state["mode"] = "hourPre"
        state["hours"] = int(re.search(r"\d+小时天气", event.raw_message).group(0).replace("小时天气", ""))
        args, kws = Command.formatToCommand(
            event.raw_message.replace(re.search(r"\d+小时天气", event.raw_message).group(0), "").strip())
    else:
        state["mode"] = "now"
        args, kws = Command.formatToCommand(event.raw_message.replace("兔兔天气查询", "天气").replace("实时天气", "").replace("天气", "").strip())

    if "more" in kws:
        state["more"] = []
        for i, m in enumerate(kws["more"].split(",")):
            state["more"].append(m.strip())
        del kws["more"]
    else:
        state["more"] = None

    # 处理城市名
    state["user_params"] = await ExtraData.getData(targetType=ExtraData.User, targetId=event.user_id,
                                                   key="kami.weather.params", default={})
    # 原始内容,除去变量
    state["params"] = {}
    state["params"].update(kws)

    argStr = Command.formatToString(*args)
    if argStr != "" or "location" in state["params"]:
        # 用户第一次输入了地点文本,或传入location参数
        state["city"] = argStr
    else:
        # 用户第一次没输入地点
        # 检查判断绑定数据有没有字典
        if "location" not in state["user_params"]:
            # 第二次输入地点文本
            await bot.send(event, message="你想查询哪里的天气呢", at_sender=True)
        else:

            state["city"] = state["user_params"].get("location")


async def sendRealTimeWeather(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    preview_message = await bot.send(event, "查询天气中...", at_sender=True)
    apikey = await ExtraData.get_global_data(key="kami.weather.key", default="")
    api_key_type = await ExtraData.get_global_data(key="kami.weather.key_type", default="dev")
    cityList = await GeoApi.lookup_city(str(state["city"]), apikey, **state["params"])
    if cityList["code"] == "200":
        city = cityList["location"][0]
        # 合成图片 失败发文字
        # 城市基本信息获取
        is_gaode = city.get("is_gaode", False)
        country = city.get("country", "Unknown")  # 国家
        name = city.get("name", "Unknown")  # 城市名
        lon = city.get("lon", "0.0")  # 经度
        lat = city.get("lat", "0.0")  # 纬度
        adm2 = city.get("adm2", "Unknown")  # 城市上级行政区名
        adm1 = city.get("adm1", "Unknown")  # 一级行政区名
        tz = city.get("tz", "Unknown")  # 时区
        city_id = city.get("id", "Unknown")  # 城市id
        rank = city.get("rank", "Unknown")
        # 城市属性
        typ = city.get("type", "Unknown")
        city_description = None
        if city_id in await ExtraData.get_resource_data(key="kami.weather.city_description", default={}):
            city_description = (
                await ExtraData.get_resource_data(key="kami.weather.city_description", default={}))[city_id]

        levels = [country, adm1, adm2, name]
        cityName = "%s %s" % (adm2, name) if adm2 != name else adm2

        unit = state["params"].get("unit", None)
        if unit == "i":
            tempUnit = "℉"
        else:
            tempUnit = "℃"

        state["params"]["location"] = city_id

        # 天气基本信息获取
        if state["mode"] == "now":
            if city.get("custom", False):
                weatherInfo = {"code": "200", "now": city.get("weatherData")}
            elif is_gaode:
                weatherInfo = await PointWeatherApi.get_now_weather("%s,%s" % (lon, lat), key=apikey, key_type=api_key_type,
                                                                    lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
            else:
                weatherInfo = await CityWeatherApi.get_now_weather(location=state["params"].get("location", "%s,%s" % (lon, lat)), key=apikey, key_type=api_key_type,
                                                                   lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
            if weatherInfo["code"] == "200":

                updateTime = weatherInfo.get("updateTime", "00-00-00T00:00+00:00")  # API响应时间
                link = weatherInfo.get("fxLink")  # 链接

                weatherData = weatherInfo.get("now", {})  # 天气数据
                obsTime = weatherData.get("obsTime", "00-00-00T00:00+00:00")  # 观测时间

                obsDate = obsTime.split("T")[0]
                obsLocalTime = obsTime.split("T")[1]

                temp = weatherData.get("temp")  # 气温℃
                feelsLike = weatherData.get("feelsLike")  # 体感温度℃
                icon = weatherData.get("icon", city.get("id"))  # 图标码
                text = weatherData.get("text")  # 天气状况文本
                wind360 = weatherData.get("wind360")  # 风向角度
                windDir = weatherData.get("windDir")  # 风向
                windScale = weatherData.get("windScale")  # 风力等级
                windSpeed = weatherData.get("windSpeed")  # 风速km/h

                humidity = weatherData.get("humidity")  # 相对湿度百分比
                precip = weatherData.get("precip")  # 小时累计降水量mm
                pressure = weatherData.get("pressure")  # 大气压
                vis = weatherData.get("vis")  # 能见度
                cloud = weatherData.get("cloud")  # 云量
                dew = weatherData.get("dew")  # 露点温度

                weather_advice = (await ExtraData.get_resource_data("kami.weather.advice", default={})).get(icon, "没有建议")
                if state["params"].get("lang", "zh") not in ["zh"]:
                    weather_advice = await Command.translate(text=weather_advice, from_lang="zh", to_lang=state["params"].get("lang", "zh"))
                    if city_description is not None:
                        city_description = await Command.translate(text=city_description, from_lang="zh", to_lang=state["params"].get("lang", "zh"))

                try:
                    font_80 = os.path.join(ExConfig.res_path, state["params"].get("font1", "fonts/MiSans-Heavy.ttf"))
                    font_60 = os.path.join(ExConfig.res_path, state["params"].get("font2", "fonts/MiSans-Semibold.ttf"))

                    base_img = Image.open(os.path.join(ExConfig.res_path, "textures/weather/mesh_4xx_b.png"))
                    weather_card: Cardimage = Cardimage(baseImg=base_img)
                    # 城市名和国家 编号

                    if is_gaode:
                        city_pos = await weather_card.addText(uvSize=(1, 1), boxSize=(0.45, 0.075), xyOffset=(0, 0),
                                                              baseAnchor=(0.05, 0.04), textAnchor=(0, 0), content=cityName,
                                                              font=font_80, color=Cardimage.hex2dec("ffffffff"))
                        poi_name = city.get("poi_name", "poi查询失败")
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.9, 0.05), xyOffset=(0, 0),
                                                   baseAnchor=(city_pos[0], city_pos[3]), textAnchor=(0, 0), content=poi_name,
                                                   font=font_80, color=Cardimage.hex2dec("ffffffff"))
                        await weather_card.addText(uvSize=(1, 1), boxSize=(1.0, 0.025), xyOffset=(0, 0),
                                                   baseAnchor=(0.95, 0.97), textAnchor=(1, 1),
                                                   content="%s-%s | %s %s Designed by SnowyKami" % (icon, "%.4f,%.4f" % (float(lon), float(lat)), obsDate, obsLocalTime),
                                                   font=font_80, color=Cardimage.hex2dec("ffdedede"))
                    else:
                        city_pos = await weather_card.addText(uvSize=(1, 1), boxSize=(0.45, 0.075), xyOffset=(0, 0),
                                                              baseAnchor=(0.05, 0.04), textAnchor=(0, 0), content=cityName,
                                                              font=font_80, color=Cardimage.hex2dec("ffffffff"))
                        await weather_card.addText(uvSize=(1, 1), boxSize=(1.0, 0.025), xyOffset=(0, 0),
                                                   baseAnchor=(0.95, 0.97), textAnchor=(1, 1),
                                                   content="%s-%s | %s %s Designed by SnowyKami" % (icon, city_id, obsDate, obsLocalTime),
                                                   font=font_80, color=Cardimage.hex2dec("ffdedede"))
                    country_pos = await weather_card.addText(uvSize=(1, 1), boxSize=(
                        0.45, Balance.clamp((city_pos[3] - city_pos[1]) / 1.2, 0.04, 0.05)), xyOffset=(0, 0),
                                                             baseAnchor=(city_pos[2] + 0.02, city_pos[1] + 0.01), textAnchor=(0, 0),
                                                             content="%s-%s" % (country, adm1),
                                                             font=font_80, color=Cardimage.hex2dec("ffdedede"))
                    # 城市描述
                    if city_description is not None:
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.025), xyOffset=(0, 0),
                                                   baseAnchor=(0.95, 0.12), textAnchor=(1, 0),
                                                   content=city_description,
                                                   font=font_80, color=Cardimage.hex2dec("ffdedede"))

                    # 观测时间城市编号

                    # 天气 状态文本 和 图片 和 温度 和 建议
                    download = True
                    if not os.path.exists(os.path.join(ExConfig.res_path, "textures/weather/icons/%s.png" % icon)):
                        download = await ExtraData.download_file("https://a.hecdn.net/img/common/icon/202106d/%s.png" % icon,
                                                                 os.path.join(ExConfig.res_path,
                                                                              "textures/weather/icons/%s.png" % icon))
                    main_text_offset = 0.015
                    try:
                        await weather_card.addImage(uvSize=(1, 1), boxSize=(0.275, 0.275), xyOffset=(0, 0),
                                                    baseAnchor=(0.5, 0.27 - main_text_offset), imgAnchor=(1, 0.5),
                                                    img=Image.open(os.path.join(ExConfig.res_path,
                                                                                "textures/weather/icons/%s.png" % icon)))
                    except BaseException:
                        await weather_card.addImage(uvSize=(1, 1), boxSize=(0.275, 0.275), xyOffset=(0, 0),
                                                    baseAnchor=(0.5, 0.27 - main_text_offset), imgAnchor=(1, 0.5),
                                                    img=Image.open(os.path.join(ExConfig.res_path,
                                                                                "textures/weather/icons/default.png")))

                    # 天气文本
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, 0.075), xyOffset=(0, 0),
                                               baseAnchor=(0.55, 0.27 - main_text_offset), textAnchor=(0, 0.1),
                                               content=text,
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    # 温度
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.3, 0.05), xyOffset=(0, 0),
                                               baseAnchor=(0.55, 0.24 - main_text_offset), textAnchor=(0, 0.9),
                                               content="%s%s" % (temp, tempUnit),
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))
                    # 建议
                    await weather_card.addText(uvSize=(1, 1), boxSize=(1, 0.04), xyOffset=(0, 0),
                                               baseAnchor=(0.5, 0.43 - main_text_offset), textAnchor=(0.5, 0.5),
                                               content=weather_advice,
                                               font=font_80, color=Cardimage.hex2dec("ffffffff"))

                    # 风向风角度 风级风速 风力图标
                    lite_font_size = 0.0275
                    sub_text_center_line = 0.525
                    wind_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.07, 0.07), xyOffset=(0, 0),
                                                                baseAnchor=(0.06, sub_text_center_line), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.res_path,
                                                                                            "textures/weather/风速.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(wind_icon_pos[2] + 0.01, sub_text_center_line), textAnchor=(0, 1),
                                               content="%s %s°" % (windDir, wind360),
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(wind_icon_pos[2] + 0.01, sub_text_center_line), textAnchor=(0, 0),
                                               content="%sLv %skm/h" % (windScale, windSpeed),
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))

                    # 体感和湿度
                    feel_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.08, 0.08), xyOffset=(0, 0),
                                                                baseAnchor=(0.34, sub_text_center_line), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.res_path,
                                                                                            "textures/weather/衣服.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(feel_icon_pos[2] + 0.01, sub_text_center_line), textAnchor=(0, 1),
                                               content="%s%s" % (feelsLike, tempUnit),
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(feel_icon_pos[2] + 0.01, sub_text_center_line), textAnchor=(0, 0),
                                               content="%shPa" % pressure,
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))

                    # 湿度和降水
                    rain_icon_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.08, 0.08), xyOffset=(0, 0),
                                                                baseAnchor=(0.58, sub_text_center_line), imgAnchor=(0.5, 0.5),
                                                                img=Image.open(os.path.join(ExConfig.res_path,
                                                                                            "textures/weather/w_湿度.png")))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(rain_icon_pos[2] + 0.008, sub_text_center_line), textAnchor=(0, 1),
                                               content="%smm" % precip,
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))
                    await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                               baseAnchor=(rain_icon_pos[2] + 0.008, sub_text_center_line), textAnchor=(0, 0),
                                               content=f"{humidity}%",
                                               font=font_60, color=Cardimage.hex2dec("ffffffff"))

                    # 太阳升起和落下
                    try:
                        sun_pos = await weather_card.addImage(uvSize=(1, 1), boxSize=(0.08, 0.08), xyOffset=(0, 0), baseAnchor=(0.82, sub_text_center_line), imgAnchor=(0.5, 0.5),
                                                              img=Image.open(os.path.join(ExConfig.res_path, "textures/weather/日出日落.png")))
                        daily_weather_data = await CityWeatherApi.get_daily_weather(location="%s,%s" % (lon, lat), key=apikey, key_type=api_key_type, days=1,
                                                                                    lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                                   baseAnchor=(sun_pos[2] + 0.008, sub_text_center_line), textAnchor=(0, 1),
                                                   content="%s" % daily_weather_data["daily"][0]["sunrise"],
                                                   font=font_60, color=Cardimage.hex2dec("ffffffff"))
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.4, lite_font_size), xyOffset=(0, 0),
                                                   baseAnchor=(sun_pos[2] + 0.008, sub_text_center_line), textAnchor=(0, 0),
                                                   content="%s" % daily_weather_data["daily"][0]["sunset"],
                                                   font=font_60, color=Cardimage.hex2dec("ffffffff"))

                    except BaseException as e:
                        pass

                    # 曲线图绘制（6小时）

                    try:
                        x_point_hourly = 0
                        hours = Balance.clamp(int(state["params"].get("hours", 8)), 0, 168)
                        if is_gaode:
                            hourly_weather_data = await CityWeatherApi.get_hourly_weather(location="%s,%s" % (lon, lat), key=apikey, hours=hours, key_type=api_key_type,
                                                                                          lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
                        else:
                            hourly_weather_data = await CityWeatherApi.get_hourly_weather(location=city_id, key=apikey, hours=hours, key_type=api_key_type,
                                                                                          lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
                        hourly_temp_max = max([float(hourly["temp"]) for hourly in hourly_weather_data["hourly"][0:hours]]) + 1
                        hourly_temp_min = min([float(hourly["temp"]) for hourly in hourly_weather_data["hourly"][0:hours]]) - 1
                        temp_section = hourly_temp_max - hourly_temp_min
                        point = []
                        for hour, hourly_data in enumerate(hourly_weather_data["hourly"][0:hours]):
                            date_hourly = hourly_data["fxTime"].split("T")[0]
                            if "+" in hourly_data["fxTime"]:
                                split_char = "+"
                            else:
                                split_char = "-"
                            time24_hourly = hourly_data["fxTime"].split("T")[1].split(split_char)[0]
                            icon_hourly = hourly_data["icon"]
                            temp_hourly = hourly_data["temp"]
                            text_hourly = hourly_data["text"]

                            x_point_hourly += 1 / (hours + 1)
                            y_high = 0.71
                            y_low = 0.87
                            uv_section = y_low - y_high
                            if temp_section != 0:
                                y_point_hourly = y_low - (float(temp_hourly) - hourly_temp_min) / temp_section * uv_section
                            else:
                                y_point_hourly = (y_low + y_high) / 2
                            point.append([x_point_hourly, y_point_hourly])

                            await weather_card.addText(uvSize=(1, 1), boxSize=(0.2, 0.028), xyOffset=(0, 0),
                                                       baseAnchor=(x_point_hourly, y_high - 0.03), textAnchor=(0.5, 0.5),
                                                       content="%s%s" % (temp_hourly, tempUnit),
                                                       font=font_60, color=Cardimage.hex2dec("ffffffff"))
                            await weather_card.addText(uvSize=(1, 1), boxSize=(0.2, 0.0275), xyOffset=(0, 0),
                                                       baseAnchor=(x_point_hourly, y_low + 0.02), textAnchor=(0.5, 0.5),
                                                       content="%s" % time24_hourly,
                                                       font=font_60, color=Cardimage.hex2dec("ffffffff"))

                            # 小时天气状态图
                            download = True
                            if not os.path.exists(os.path.join(ExConfig.res_path, "textures/weather/icons/%s.png" % icon_hourly)):
                                download = await ExtraData.download_file("https://a.hecdn.net/img/common/icon/202106d/%s.png" % icon_hourly,
                                                                         os.path.join(ExConfig.res_path,
                                                                                      "textures/weather/icons/%s.png" % icon_hourly))

                            try:
                                await weather_card.addImage(uvSize=(1, 1), boxSize=(0.075, 0.075), xyOffset=(0, 0),
                                                            baseAnchor=(x_point_hourly, y_high - 0.08), imgAnchor=(0.5, 0.5),
                                                            img=Image.open(os.path.join(ExConfig.res_path,
                                                                                        "textures/weather/icons/%s.png" % icon_hourly)))
                            except BaseException as e:
                                await Session.sendException(bot, event, state, e)
                                await weather_card.addText(uvSize=(1, 1), boxSize=(0.075, 0.075), xyOffset=(0, 0),
                                                           baseAnchor=(x_point_hourly, y_high - 0.08), textAnchor=(0.5, 0.5),
                                                           content="%s" % icon_hourly)
                            # 圆点 画线
                            if hour == 0:
                                await weather_card.addImage(uvSize=(1, 1), boxSize=(0.025, 0.025), xyOffset=(0, 0),
                                                            baseAnchor=(x_point_hourly, y_point_hourly), imgAnchor=(0.5, 0.5),
                                                            img=Image.open(os.path.join(ExConfig.res_path,
                                                                                        "textures/weather/around_point.png")))
                            else:
                                await weather_card.addImage(uvSize=(1, 1), boxSize=(0.025, 0.025), xyOffset=(0, 0),
                                                            baseAnchor=(x_point_hourly, y_point_hourly), imgAnchor=(0.5, 0.5),
                                                            img=Image.open(os.path.join(ExConfig.res_path,
                                                                                        "textures/weather/around_point.png")))
                                await weather_card.drawLine(uvSize=(1, 1), p1=(point[hour - 1]), p2=[x_point_hourly, y_point_hourly], width=10)
                    except BaseException as e:
                        await weather_card.addText(uvSize=(1, 1), boxSize=(0.6, 0.2), xyOffset=(0, 0),
                                                   baseAnchor=(0.5, 0.75), textAnchor=(0.5, 0.5),
                                                   content="未查询到逐小时天气数据",
                                                   font=font_60, color=Cardimage.hex2dec("ffffffff"))

                    # 体感湿度

                    await bot.send(event,
                                   message=MessageSegment(type="image",
                                                          data={"file": "file:///%s" % await weather_card.getPath(), }))
                    await weather_card.delete()

                except BaseException as ae:
                    await Session.sendException(bot, event, state, ae)

            else:
                await bot.send(event, message="%s查询失败: %s\nhttps://dev.qweather.com/docs/resource/status-code/" % (
                    "实时天气", weatherInfo["code"]), at_sender=True)

        elif state["mode"] == "multiPre":
            weatherData = await CityWeatherApi.get_daily_weather(location=city_id, key=apikey, days=state["days"], key_type=api_key_type,
                                                                 lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
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
            weatherData = await CityWeatherApi.get_hourly_weather(location=city_id, key=apikey, key_type=api_key_type, hours=state["hours"],
                                                                  lang=state["params"].get("lang", "zh"), unit=state["params"].get("unit", "m"))
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
    await bot.delete_msg(message_id=preview_message["message_id"])

    await Log.plugin_log("kami.weather", "用户:%s查询了%s天气，状态码是%s" % (event.user_id, event.raw_message, cityList["code"]))
