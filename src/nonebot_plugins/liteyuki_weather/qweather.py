import datetime

from nonebot import require, on_endswith
from nonebot.adapters import satori
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.internal.matcher import Matcher

from src.utils.base.config import get_config
from src.utils.base.ly_typing import T_MessageEvent

from .qw_api import *
from src.utils.base.data_manager import User, user_db
from src.utils.base.language import Language, get_user_lang
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image
from src.utils import event as event_utils

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, MultiVar, Arparma, UniMessage

wx_alc = on_alconna(
    aliases={"天气"},
    command=Alconna(
        "weather",
        Args["keywords", MultiVar(str), []],
    ),
)


@wx_alc.handle()
async def _(result: Arparma, event: T_MessageEvent, matcher: Matcher):
    """await alconna.send("weather", city)"""
    kws = result.main_args.get("keywords")
    image = await get_weather_now_card(matcher, event, kws)
    await wx_alc.finish(UniMessage.image(raw=image))


@on_endswith(("天气", "weather")).handle()
async def _(event: T_MessageEvent, matcher: Matcher):
    """await alconna.send("weather", city)"""
    # kws = event.message.extract_plain_text()
    kws = event.get_plaintext()
    image = await get_weather_now_card(matcher, event, [kws.replace("天气", "").replace("weather", "")], False)
    if isinstance(event, satori.event.Event):
        await matcher.finish(satori.MessageSegment.image(raw=image, mime="image/png"))
    else:
        await matcher.finish(MessageSegment.image(image))


async def get_weather_now_card(matcher: Matcher, event: T_MessageEvent, keyword: list[str], tip: bool = True):
    ulang = get_user_lang(event_utils.get_user_id(event))
    qw_lang = get_qw_lang(ulang.lang_code)
    key = get_config("weather_key")
    is_dev = get_memory_data("weather.is_dev", True)
    extra_info = get_config("weather_extra_info")
    attr = get_config("weather_attr")
    
    user: User = user_db.where_one(User(), "user_id = ?", event_utils.get_user_id(event), default=User())
    # params
    unit = user.profile.get("unit", "m")
    stored_location = user.profile.get("location", None)

    if not key:
        await matcher.finish(ulang.get("weather.no_key") if tip else None)

    if keyword:
        if len(keyword) >= 2:
            adm = keyword[0]
            city = keyword[-1]
        else:
            adm = ""
            city = keyword[0]
        city_info = await city_lookup(city, key, adm=adm, lang=qw_lang)
        city_name = " ".join(keyword)
    else:
        if not stored_location:
            await matcher.finish(ulang.get("liteyuki.invalid_command", TEXT="location") if tip else None)
        city_info = await city_lookup(stored_location, key, lang=qw_lang)
        city_name = stored_location
    if city_info.code == "200":
        location_data = city_info.location[0]
    else:
        await matcher.finish(ulang.get("weather.city_not_found", CITY=city_name) if tip else None)
    weather_now = await get_weather_now(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    weather_daily = await get_weather_daily(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    weather_hourly = await get_weather_hourly(key, location_data.id, lang=qw_lang, unit=unit, dev=is_dev)
    aqi = await get_airquality(key, location_data.id, lang=qw_lang, dev=is_dev)
    weather_astronomy = await get_astronomy(key, location_data.id, date=datetime.datetime.now().strftime('%Y%m%d'), dev=is_dev)

    image = await template2image(
        template=get_path("templates/weather_now.html", abs_path=True),
        templates={
                "data": {
                        "params"       : {
                                "unit": unit,
                                "lang": ulang.lang_code,
                        },
                        "weatherNow"        : weather_now,
                        "weatherDaily"      : weather_daily,
                        "weatherHourly"     : weather_hourly,
                        "aqi"               : aqi,
                        "location"          : location_data.dump(),
                        "localization"      : get_local_data(ulang.lang_code),
                        "weatherAstronomy"  : weather_astronomy,
                        "is_dev"            : 1 if is_dev else 0,
                        "extra_info"        : extra_info,
                        "attr"              : attr

                }
        },
    )
    return image
