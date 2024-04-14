from liteyuki.utils.base.data import LiteModel


class Location(LiteModel):
    name: str = ""
    id: str = ""
    lat: str = ""
    lon: str = ""
    adm2: str = ""
    adm1: str = ""
    country: str = ""
    tz: str = ""
    utcOffset: str = ""
    isDst: str = ""
    type: str = ""
    rank: str = ""
    fxLink: str = ""
    sources: str = ""
    license: str = ""


class CityLookupResponse(LiteModel):
    code: str = ""
    location: Location = Location()


class WeatherNow(LiteModel):
    obsTime: str = ""
    temp: str = ""
    feelsLike: str = ""
    icon: str = ""
    text: str = ""
    wind360: str = ""
    windDir: str = ""
    windScale: str = ""
    windSpeed: str = ""
    humidity: str = ""
    precip: str = ""
    pressure: str = ""
    vis: str = ""
    cloud: str = ""
    dew: str = ""
    sources: str = ""
    license: str = ""


class WeatherNowResponse(LiteModel):
    code: str = ""
    updateTime: str = ""
    fxLink: str = ""
    now: WeatherNow = WeatherNow()
