from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot.utils import run_sync

from .text import *
from .utils import *
from .weather_api import *
from .weather_card import *
from ...liteyuki_api.data import Data
from ...liteyuki_api.utils import *

set_key = on_command("配置天气key", permission=SUPERUSER)
bind_location = on_command("绑定天气城市")
query_weather_now = on_message(rule=WEATHER_NOW)


@set_key.handle()
async def _(arg: Message = CommandArg()):
    key = str(arg)
    resp = await run_sync(simple_request_get)("https://api.qweather.com/v7/weather/now?location=101040300&key=%s" % key)
    code = (resp.json())["code"]
    if code == "200":
        key_type = "com"
    else:
        resp = await run_sync(simple_request_get)("https://devapi.qweather.com/v7/weather/now?location=101040300&key=%s" % key)
        code = (resp.json())["code"]
        if code == "200":
            key_type = "dev"
        else:
            key_type = None
            await set_key.finish("key无效")
    await Data(Data.globals, "qweather").set_many({"key": key, "key_type": key_type})
    await set_key.send(f"和风天气key设置成功：{'商业版' if key_type == 'com' else '开发版'}")


@bind_location.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    await key_check(bind_location)
    args, kwargs = Command.formatToCommand(str(arg))
    # 输入内容
    args_2 = Command.formatToString(*args)

    city_lookup_result: CityLookup = await city_lookup(args_2, **kwargs)
    if city_lookup_result is None:
        await bind_location.finish(text.location_found_failed, at_sender=True)
    else:
        location = city_lookup_result.location[0]
        await Data(Data.users, event.user_id).set("weather_location",
                                                  {
                                                      "lat": location.lat,
                                                      "lon": location.lon,
                                                      "lang": kwargs.get("lang", "zh-hans"),
                                                      "unit": kwargs.get("unit", "m")}
                                                  )
        await bind_location.finish(f"天气查询城市已设置为:{format_location_show_name([location.country, location.adm1, location.adm2, location.name])}")


@query_weather_now.handle()
async def _(event: MessageEvent, state: T_State):
    args, kwargs = Command.formatToCommand(str(event.message))

    input_location = " ".join(args)
    for weather_lang_name in weather_lang_names:
        input_location = input_location.replace(weather_lang_name, "")
    input_location = input_location.strip()

    stored_location = await Data(Data.users, event.user_id).get("weather_location", None)
    state["location"] = None
    state["lang"] = kwargs.get("lang", "zh-hans" if stored_location is None else stored_location.get("lang", "zh-hans"))
    state["unit"] = kwargs.get("unit", "m" if stored_location is None else stored_location.get("unit", "m"))

    if input_location == "" and stored_location is None:
        """既无输入也无储存，询问地点"""
        del state["location"]
        await query_weather_now.send(text.where_you_want_know, at_sender=True)
    elif input_location != "":
        """用户有输入搜索地点"""
        searched_locations: CityLookup = (await city_lookup(input_location))
        if searched_locations is None:
            await query_weather_now.finish(text.location_found_failed, at_sender=True)
        else:
            location = searched_locations.location[0]
            state["location"] = {"lat": location.lat, "lon": location.lon}
    else:
        state["location"] = stored_location


@query_weather_now.got(key="location")
async def _(state: T_State):
    location_xy: dict = state["location"]
    if isinstance(state["location"], Message):
        input_location = str(state["location"])
        for weather_lang_name in weather_lang_names:
            input_location = input_location.replace(weather_lang_name, "")
        city_lookup_result: CityLookup = await city_lookup(input_location)
        if city_lookup_result is None:
            await query_weather_now.finish(location_found_failed, at_sender=True)
        else:
            location = city_lookup_result.location[0]
            location_xy = {"lat": location.lat, "lon": location.lon}
    city_lookup_model = await city_lookup("",
                                    location=f"{location_xy.get('lon')},{location_xy.get('lat')}",
                                    lang=state["lang"]
                                    )
    if city_lookup_model is None:
        await query_weather_now.finish(location_found_failed, at_sender=True)
    args = (f"{location_xy.get('lon')},{location_xy.get('lat')}", state["lang"], state["unit"])
    weather_now_model = await weather_now(*args)
    air_now_model = await air_now(*args)
    weather_hourly_model = await weather_hourly(*args)
    weather_daily_model = await weather_daily(*args)
    if state["unit"] == "i":
        unit = "℉"
    else:
        unit = "℃"
    canvas: Canvas = await run_sync(generate_weather_now)(location=city_lookup_model.location[0], weather_now=weather_now_model,
                                                          weather_hourly=weather_hourly_model, weather_daily=weather_daily_model, air=air_now_model, unit=unit, lang=state["lang"])

    await query_weather_now.finish(MessageSegment.image(file=f"file:///{await run_sync(canvas.export_cache)()}"))
    await run_sync(canvas.delete)()


__plugin_meta__ = PluginMetadata(
    name="轻雪天气",
    description="轻雪内置和风天气插件",
    usage='•配置天气key\n\n'
          '•<地名>天气\n\n'
          '•绑定天气城市<地名>\n\n',
    extra={
        "liteyuki_plugin": True,
    }
)
