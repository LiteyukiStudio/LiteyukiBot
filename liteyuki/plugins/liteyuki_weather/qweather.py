from nonebot import require
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.internal.matcher import Matcher

from liteyuki.utils.base.config import get_config
from liteyuki.utils.base.ly_typing import T_MessageEvent

from .qw_api import *
from ...utils.base.data_manager import User, user_db
from ...utils.base.language import get_user_lang
from ...utils.base.resource import get_path
from ...utils.message.html_tool import template2image

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, MultiVar, Arparma


@on_alconna(
    aliases={"天气"},
    command=Alconna(
        "weather",
        Args["keywords", MultiVar(str), []],
    ),
).handle()
async def _(result: Arparma, event: T_MessageEvent, matcher: Matcher):
    """await alconna.send("weather", city)"""
    ulang = get_user_lang(str(event.user_id))
    qw_lang = get_qw_lang(ulang.lang_code)
    key = get_config("weather_key")
    is_dev = get_config("weather_dev")

    user: User = user_db.first(User(), "user_id = ?", str(event.user_id), default=User())

    # params
    unit = user.profile.get("unit", "m")
    stored_location = user.profile.get("location", None)

    if not key:
        await matcher.finish(ulang.get("weather.no_key"))

    kws = result.main_args.get("keywords")
    if kws:
        if len(kws) >= 2:
            adm = kws[0]
            city = kws[-1]
        else:
            adm = ""
            city = kws[0]
        city_info = await city_lookup(city, key, adm=adm, lang=qw_lang)
        city_name = " ".join(kws)
    else:
        if not stored_location:
            await matcher.finish(ulang.get("liteyuki.invalid_command", TEXT="location"))
        city_info = await city_lookup(stored_location, key, lang=qw_lang)
        city_name = stored_location
    if city_info.code == "200":
        location_data = city_info.location[0]
    else:
        await matcher.finish(ulang.get("weather.city_not_found", CITY=city_name))

    weather_now = await get_weather_now(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    weather_daily = await get_weather_daily(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    weather_hourly = await get_weather_hourly(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    aqi = await get_airquality(key, location_data.id, lang=qw_lang, dev=is_dev)

    image = await template2image(
        template=get_path("templates/weather_now.html", abs_path=True),
        templates={
                "data": {
                        "params"       : {
                                "unit": unit,
                                "lang": ulang.lang_code,
                        },
                        "weatherNow"   : weather_now,
                        "weatherDaily" : weather_daily,
                        "weatherHourly": weather_hourly,
                        "aqi"          : aqi,
                        "location"     : location_data.dump(),
                }
        },
        debug=True,
        wait=1
    )
    await matcher.finish(MessageSegment.image(image))
