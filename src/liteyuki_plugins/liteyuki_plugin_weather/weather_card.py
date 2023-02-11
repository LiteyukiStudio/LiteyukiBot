import os
import random
import time

import nonebot

from .model import *
from ...liteyuki_api.canvas import *
from .utils import *
from .text import *
from PIL import Image

from ...liteyuki_api.utils import download_file, generate_signature

default_font = Font.HYWH_85w


def generate_weather_now(location: Location, weather_now: WeatherNow, weather_hourly: WeatherHourly, weather_daily: WeatherDaily, air: AirNow, unit="℃", lang="zh-hans") -> Canvas:
    bg_size = (1080, 2400)
    side_width = 25
    down_width = 50
    distance_height = 25
    base_fillet = 15
    base_cover = (0, 0, 0, 128)
    drawing_path = os.path.join(Path.data, "liteyuki/drawing")

    distance_height_scale = distance_height / (bg_size[1] - 2 * side_width)
    part_now_height_scale = 0.27
    tag_part_height_scale = 0.13
    hourly_part_height_scale = 0.15
    daily_part_height_scale = 0.25
    ad_part_height_scale = 0.15

    if len(os.listdir(drawing_path)) > 0:
        base_img = Utils.central_clip_by_ratio(Image.open(os.path.join(Path.data, f"liteyuki/drawing/{random.choice(os.listdir(drawing_path))}")), bg_size)
    else:
        base_img = Image.new(mode="RGBA", size=bg_size, color=(255, 255, 255, 255))
    canvas = Canvas(base_img)
    canvas.content = Panel(
        uv_size=bg_size,
        box_size=(bg_size[0] - 2 * side_width, bg_size[1] - side_width - down_width),
        parent_point=(0.5, side_width / bg_size[1]),
        point=(0.5, 0)
    )
    # Part Now Weather
    canvas.content.now_part = Rectangle(
        uv_size=(1, 1), box_size=(1, part_now_height_scale), parent_point=(0.5, 0), point=(0.5, 0), color=base_cover, fillet=base_fillet
    )
    # 时间戳
    a_o_s = "+" if "+" in weather_now.now.obsTime else "-"
    date_text = weather_now.now.obsTime.split("T")[0]
    time_text = weather_now.now.obsTime.split("T")[1].split(a_o_s)[0]
    day_text = get_day(time.localtime().tm_wday + 1, lang)

    canvas.content.now_part.datetime = Text(
        uv_size=(1, 1), box_size=(0.8, 0.06), parent_point=(0.015, 0.024), point=(0, 0), dp=1,
        text=f"{date_text} {day_text} {time_text}",
        font=default_font, color=(220, 220, 220, 255), anchor="lt"
    )
    country_province_name, location_name = format_location_show_name_2([location.country, location.adm1, location.adm2, location.name])
    # 国家 中国 重庆市
    canvas.content.now_part.cp_name = Text(
        uv_size=(1, 1), box_size=(0.8, 0.075), parent_point=(0.5, 0.17), point=(0.5, 0.5),
        text=country_province_name, font=default_font, color=(220, 220, 220, 255), anchor="lt"
    )
    # 地点名 沙坪坝
    canvas.content.now_part.loc_name = Text(
        uv_size=(1, 1), box_size=(0.75, 0.13), parent_point=(0.5, 0.26), point=(0.5, 0),
        text=location_name, font=default_font, anchor="lt"
    )
    state_icon_path_day = os.path.join(Path.cache, f"weather/{weather_now.now.icon}.png")
    download_file(f"https://a.hecdn.net/img/common/icon/202106d/{weather_now.now.icon}.png", state_icon_path_day)
    # 状态区
    canvas.content.now_part.state_icon = Img(
        uv_size=(1, 1), box_size=(0.5, 0.4), parent_point=(0.5, 0.58), point=(1, 0.5),
        img=Image.open(state_icon_path_day)
    )
    canvas.content.now_part.temp = Text(
        uv_size=(1, 1), box_size=(0.5, 0.13), parent_point=(0.52, 0.49), point=(0, 0.5),
        text=f"{weather_now.now.temp}{unit}", font=default_font
    )
    canvas.content.now_part.state_text = Text(
        uv_size=(1, 1), box_size=(0.5, 0.12), parent_point=(0.52, 0.68), point=(0, 0.5),
        text=weather_now.now.text, font=default_font
    )

    canvas.content.tag_part = Rectangle(
        uv_size=(1, 1), box_size=(1, tag_part_height_scale), parent_point=(0.5, part_now_height_scale + distance_height_scale), point=(0.5, 0), color=base_cover, fillet=base_fillet
    )
    if air is not None:
        AQI = int(air.now.aqi)
        if AQI < 75:
            arc_color = Color.hex2dec("FF55AF7B")
        elif AQI < 150:
            arc_color = Color.hex2dec("FFFAC230")
        elif AQI < 300:
            arc_color = Color.hex2dec("FFFA9D5A")
        else:
            arc_color = Color.hex2dec("FFEB4537")
        AQI_text = f" AQI {AQI} {air.now.category} "
        props = [
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_WIND_ADD_HURT.png"),
                "name": {
                    "zh-hans": f"风向  {weather_now.now.windDir}  {weather_now.now.wind360}°",
                    "en": f"Dir  {weather_now.now.windDir}  {weather_now.now.wind360}°"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_CHARGE_EFFICIENCY.png"),
                "name": {
                    "zh-hans": f"风力  {weather_now.now.windScale}级 {weather_now.now.windSpeed}km/h",
                    "en": f"Scale  Lv.{weather_now.now.windScale} {weather_now.now.windSpeed}km/h",
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_WATER_ADD_HURT.png"),
                "name": {
                    "zh-hans": f"湿度  {weather_now.now.humidity}%",
                    "en": f"Humidity  {weather_now.now.humidity}%"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_HEAL_ADD.png"),
                "name": {
                    "zh-hans": f"体感  {weather_now.now.feelsLike}{unit}",
                    "en": f"Feel  {weather_now.now.feelsLike}{unit}"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_HP.png"),
                "name": {
                    "zh-hans": f"降水  {weather_now.now.precip}mm",
                    "en": f"Precip  {weather_now.now.precip}mm"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/genshin/FIGHT_PROP_CRITICAL_HURT.png"),
                "name": {
                    "zh-hans": f"气压  {weather_now.now.pressure}hPa",
                    "en": f"Atm  {weather_now.now.pressure}hPa"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/qweather/sunrise.png"),
                "name": {
                    "zh-hans": f"日出  {weather_daily.daily[0].sunrise if weather_daily is not None else no_data}",
                    "en": f"Sunrise  {weather_daily.daily[0].sunrise if weather_daily is not None else no_data}"
                }
            },
            {
                "icon": os.path.join(Path.res, "textures/qweather/sunset.png"),
                "name": {
                    "zh-hans": f"日落  {weather_daily.daily[0].sunset if weather_daily is not None else no_data}",
                    "en": f"Sunset  {weather_daily.daily[0].sunset if weather_daily is not None else no_data}"
                }
            },
        ]
        count_for_each_row = 2
        prop_dx = 1 / count_for_each_row
        prop_dy = 1 / (len(props) // count_for_each_row)
        for prop_i, prop in enumerate(props):
            row = prop_i // count_for_each_row
            columns = prop_i % count_for_each_row
            prop_panel = canvas.content.tag_part.__dict__[f"prop_{prop_i}"] = Panel(
                uv_size=(1, 1), box_size=(prop_dx, prop_dy), parent_point=(prop_dx * columns, prop_dy * row), point=(0, 0)
            )
            prop_panel.icon = Img(
                uv_size=(1, 1), box_size=(0.6, 0.55), parent_point=(0.11, 0.5), point=(0.5, 0.5), img=Image.open(prop["icon"])
            )
            prop_panel.text = Text(
                uv_size=(1, 1), box_size=(0.6, 0.5), parent_point=(0.19, 0.5), point=(0, 0.5), text=prop["name"].get(lang, prop["name"]["en"]), force_size=True, font=default_font
            )

    else:
        AQI_text = f" No AQI data "
        arc_color = Color.hex2dec("FF55AF7B")
        canvas.content.tag_part.text = Text(
            uv_size=(1, 1), box_size=(0.6, 0.5), parent_point=(0.5, 0.5), point=(0.5, 0.5), text=no_detailed_data, font=default_font
        )
    canvas.content.now_part.aqi = Text(
        uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(0.5, 0.89), point=(0.5, 0.5),
        text=AQI_text, font=default_font, fill=arc_color, fillet=8
    )

    # 小时、日共同变量
    white_dot_high_scale = 0.06
    icon_high_scale = 0.18
    # 每小时温度部分
    canvas.content.hourly_part = Rectangle(
        uv_size=(1, 1), box_size=(1, hourly_part_height_scale), parent_point=(0.5, part_now_height_scale + tag_part_height_scale + distance_height_scale * 2), point=(0.5, 0),
        color=base_cover, fillet=base_fillet
    )
    hourly_limited_list = weather_hourly.hourly[0:13]
    if weather_hourly is not None:
        temp_list = [float(hour.temp) for hour in hourly_limited_list]
        min_temp: float = min(temp_list)
        max_temp: float = max(temp_list)
        if min_temp == max_temp:
            min_temp -= 1
            max_temp += 1
        delta_temp = max_temp - min_temp
        hour_dx = 1 / len(temp_list)
        up_line = 0.6
        down_line = 0.85
        point_x, point_y = 0, 0
        for hour_i, hour in enumerate(hourly_limited_list):
            last_point = (point_x, point_y)
            point_x = (hour_dx * (hour_i + 0.5))
            point_y = down_line - ((down_line - up_line) * (float(hour.temp) - min_temp) / delta_temp)

            hour_panel = canvas.content.hourly_part.__dict__[f"hour_{hour_i}"] = Panel(
                uv_size=(1, 1), box_size=(hour_dx, 1), parent_point=(hour_dx * hour_i, 0), point=(0, 0)
            )
            hour_panel.point = Img(
                uv_size=(1, 1), box_size=(1, white_dot_high_scale), parent_point=(0.5, point_y), point=(0.5, 0.5),
                img=Image.open(os.path.join(Path.res, "textures/qweather/white_dot.png"))
            )
            # 连线
            if hour_i > 0:
                canvas.draw_line("content.hourly_part", p1=last_point, p2=(point_x, point_y), color=Color.WHITE, width=7)
            if hour_i % 2 == 1:
                # 双数小时加时间天气状态
                state_icon_path_day = os.path.join(Path.cache, f"weather/{hour.icon}")
                download_file(f"https://a.hecdn.net/img/common/icon/202106d/{hour.icon}.png", state_icon_path_day)
                add_or_sub = "+" if "+" in hour.fxTime else "-"
                time_text = hour.fxTime.split("T")[1].split(add_or_sub)[0]
                hour_panel.time = Text(
                    uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(0.5, 0.12), point=(0.5, 0.5),
                    text=time_text, force_size=True, font=default_font
                )
                hour_panel.icon = Img(
                    uv_size=(1, 1), box_size=(10, icon_high_scale), parent_point=(0.5, 0.3), point=(0.5, 0.5),
                    img=Image.open(state_icon_path_day)
                )
                hour_panel.temp = Text(
                    uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(0.5, point_y - 0.08), point=(0.5, 1),
                    text=f"{hour.temp}", force_size=True, font=default_font
                )
                temp_pos = canvas.get_parent_box(f"content.hourly_part.hour_{hour_i}.temp")
                hour_panel.character = Text(
                    uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(temp_pos[2], temp_pos[1]), point=(0, 0),
                    text="°", force_size=True, font=default_font
                )
            last_point = (point_x, point_y)
    else:
        canvas.content.hourly_part.text = Text(
            uv_size=(1, 1), box_size=(0.6, 0.5), parent_point=(0.5, 0.5), point=(0.5, 0.5), text=no_detailed_data, font=default_font
        )

    # 每天天气部分
    daily_control_scale = hourly_part_height_scale / daily_part_height_scale
    canvas.content.daily_part = Rectangle(
        uv_size=(1, 1), box_size=(1, daily_part_height_scale),
        parent_point=(0.5, part_now_height_scale + tag_part_height_scale + hourly_part_height_scale + distance_height_scale * 3), point=(0.5, 0),
        color=base_cover, fillet=base_fillet
    )
    if weather_daily is not None:
        temp_min_list = [float(day.tempMin) for day in weather_daily.daily]
        temp_max_list = [float(day.tempMax) for day in weather_daily.daily]
        temp_list_time_2 = temp_min_list + temp_max_list
        min_temp: float = min(temp_list_time_2)
        max_temp: float = max(temp_list_time_2)
        if min_temp == max_temp:
            min_temp -= 1
            max_temp += 1
        delta_temp = max_temp - min_temp
        day_dx = 1 / len(temp_min_list)
        up_line = 0.51
        down_line = 0.75
        last_point_min, last_point_max = (0, 0), (0, 0)
        today = time.localtime().tm_wday
        for day_i, day in enumerate(weather_daily.daily):

            point_max = day_dx * (day_i + 0.5), down_line - ((down_line - up_line) * (float(day.tempMax) - min_temp) / delta_temp)
            point_min = day_dx * (day_i + 0.5), down_line - ((down_line - up_line) * (float(day.tempMin) - min_temp) / delta_temp)

            day_panel = canvas.content.daily_part.__dict__[f"day_{day_i}"] = Panel(
                uv_size=(1, 1), box_size=(day_dx, 1), parent_point=(day_dx * day_i, 0), point=(0, 0)
            )
            day_panel.point_min = Img(
                uv_size=(1, 1), box_size=(1, white_dot_high_scale * daily_control_scale), parent_point=(0.5, point_min[1]), point=(0.5, 0.5),
                img=Image.open(os.path.join(Path.res, "textures/qweather/white_dot.png"))
            )
            day_panel.point_max = Img(
                uv_size=(1, 1), box_size=(1, white_dot_high_scale * daily_control_scale), parent_point=(0.5, point_max[1]), point=(0.5, 0.5),
                img=Image.open(os.path.join(Path.res, "textures/qweather/white_dot.png"))
            )
            # 连线
            if day_i > 0:
                canvas.draw_line("content.daily_part", p1=last_point_min, p2=point_min, color=Color.WHITE, width=7)
                canvas.draw_line("content.daily_part", p1=last_point_max, p2=point_max, color=Color.WHITE, width=7)

            state_icon_path_day = os.path.join(Path.cache, f"weather/{day.iconDay}.png")
            state_icon_path_night = os.path.join(Path.cache, f"weather/{day.iconNight}.png")
            state_icon_path_moon = os.path.join(Path.cache, f"weather/{day.moonPhaseIcon}.png")
            download_file(f"https://a.hecdn.net/img/common/icon/202106d/{day.iconDay}.png", state_icon_path_day)
            download_file(f"https://a.hecdn.net/img/common/icon/202106d/{day.iconNight}.png", state_icon_path_night)
            download_file(f"https://a.hecdn.net/img/common/icon/202106d/{day.moonPhaseIcon}.png", state_icon_path_moon)
            time_text = ".".join(day.fxDate.split("-")[1:])
            # 时间和图标

            day_panel.date = Text(
                uv_size=(1, 1), box_size=(0.5, 0.1 * daily_control_scale), parent_point=(0.5, 0.12 * daily_control_scale), point=(0.5, 0.5),
                text=time_text, force_size=True, font=default_font
            )
            day_panel.day = Text(
                uv_size=(1, 1), box_size=(0.5, 0.09 * daily_control_scale), parent_point=(0.5, 0.24 * daily_control_scale), point=(0.5, 0.5),
                text=get_day(today % 7 + 1, lang), force_size=True, font=default_font
            )
            day_panel.day_icon = Img(
                uv_size=(1, 1), box_size=(10, icon_high_scale * daily_control_scale), parent_point=(0.5, 0.41 * daily_control_scale), point=(0.5, 0.5),
                img=Image.open(state_icon_path_day)
            )
            day_panel.day_night_icon = Img(
                uv_size=(1, 1), box_size=(10, icon_high_scale * daily_control_scale * 0.8), parent_point=(0.5, 0.56 * daily_control_scale), point=(0, 0.5),
                img=Image.open(state_icon_path_night)
            )
            day_panel.day_moon_icon = Img(
                uv_size=(1, 1), box_size=(10, icon_high_scale * daily_control_scale * 0.8), parent_point=(0.5, 0.56 * daily_control_scale), point=(1, 0.5),
                img=Image.open(state_icon_path_moon)
            )
            # 最大最小天气度数
            day_panel.temp_min = Text(
                uv_size=(1, 1), box_size=(0.5, 0.1 * daily_control_scale), parent_point=(0.5, point_min[1] + 0.08 * daily_control_scale), point=(0.5, 0),
                text=f"{day.tempMin}", force_size=True, font=default_font
            )
            day_panel.temp_max = Text(
                uv_size=(1, 1), box_size=(0.5, 0.1 * daily_control_scale), parent_point=(0.5, point_max[1] - 0.08 * daily_control_scale), point=(0.5, 1),
                text=f"{day.tempMax}", force_size=True, font=default_font
            )
            temp_pos_min = canvas.get_parent_box(f"content.daily_part.day_{day_i}.temp_min")
            temp_pos_max = canvas.get_parent_box(f"content.daily_part.day_{day_i}.temp_max")
            # 度数符号
            day_panel.character_min = Text(
                uv_size=(1, 1), box_size=(0.5, 0.1 * daily_control_scale), parent_point=(temp_pos_min[2], temp_pos_min[1]), point=(0, 0),
                text="°", force_size=True, font=default_font
            )
            day_panel.character_max = Text(
                uv_size=(1, 1), box_size=(0.5, 0.1 * daily_control_scale), parent_point=(temp_pos_max[2], temp_pos_max[1]), point=(0, 0),
                text="°", force_size=True, font=default_font
            )
            last_point_min = point_min
            last_point_max = point_max
            today += 1
    else:
        canvas.content.daily_part.text = Text(
            uv_size=(1, 1), box_size=(0.6, 0.5 * daily_control_scale), parent_point=(0.5, 0.5), point=(0.5, 0.5), text=no_detailed_data, font=default_font
        )

    ad_panel = canvas.content.ad_part = Rectangle(
        uv_size=(1, 1), box_size=(1, ad_part_height_scale),
        parent_point=(0.5, part_now_height_scale + tag_part_height_scale + hourly_part_height_scale + daily_part_height_scale + distance_height_scale * 4), point=(0.5, 0),
        color=base_cover, fillet=base_fillet
    )
    ad_panel_size = canvas.get_actual_pixel_size("content.ad_part")
    ad_path = os.path.join(Path.data, "liteyuki/ads")

    if len(os.listdir(ad_path)) > 0:
        ad_img_path = os.path.join(ad_path, random.choice(os.listdir(ad_path)))
        ad_img = Image.open(ad_img_path)
        ad_panel.ad_img = Img(
            uv_size=(1, 1), box_size=(1, 1),
            parent_point=(0.5, 0.5), point=(0.5, 0.5), img=Graphical.rectangle(size=ad_panel_size, fillet=base_fillet,
                                                                               img=ad_img)
        )
        ad_name = f'  {".".join(os.path.basename(ad_img_path).replace("#", "").split(".")[0:-1])}  '
        ad_panel.ad_img.text = Text(
            uv_size=(1, 1), box_size=(1, 0.12),
            parent_point=(0, 1), point=(0, 1), text=ad_name,
            fillet=base_fillet, fill=base_cover, dp=1
        )

    # 轻雪最后签名
    canvas.signature = Text(
        uv_size=(1, 1), box_size=(1, 0.018), parent_point=(0.5, 0.995), point=(0.5, 1), text=f" {generate_signature} ", font=default_font, dp=1, fill=base_cover, fillet=base_fillet
    )
    return canvas
