from nonebot import on_command
from liteyuki.utils.data import LiteModel


class Location(LiteModel):
    name: str = ""
    id: str = ""
    country: str = ""

class WeatherNow(LiteModel):
    time: str = ""
    city: str = ""


weather = on_command("weather", aliases={"天气", "查天气", "天气预报", "查天气预报"})
weather_now = on_command("weather_now", aliases={"实时天气", "查实时天气", "实时天气预报", "查实时天气预报"})
weather_forecast = on_command("weather_forecast", aliases={"天气预报", "查天气预报", "未来天气", "查未来天气"})
weather_warning = on_command("weather_warning", aliases={"天气预警", "查天气预警", "天气警告", "查天气警告"})
weather_life = on_command("weather_life", aliases={"生活指数", "查生活指数", "生活指数预报", "查生活指数预报"})
weather_air = on_command("weather_air", aliases={"空气质量", "查空气质量", "空气质量预报", "查空气质量预报"})
weather_rain = on_command("weather_rain", aliases={"降雨预报", "查降雨预报", "降雨量", "查降雨量"})
weather_snow = on_command("weather_snow", aliases={"降雪预报", "查降雪预报", "降雪量", "查降雪量"})


@weather.handle()
async def handle_weather(bot, event):
    args = str(event.get_message()).strip()
    if not args:
        await weather.finish("请输入要查询的城市")
    else:
        pass


@weather_now.handle()
async def handle_weather_now(bot, event):
    pass

@weather_forecast.handle()
async def handle_weather_forecast(bot, event):
    pass
