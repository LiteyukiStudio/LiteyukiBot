
from liteyuki.utils.data import LiteModel


class Location(LiteModel):
    name: str = ""
    id: str = ""
    country: str = ""

class WeatherNow(LiteModel):
    time: str = ""
    city: str = ""

