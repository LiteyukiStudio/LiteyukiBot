from typing import Dict, List

from pydantic import BaseModel


class Now(BaseModel):
    obsTime: str
    temp: str
    feelsLike: str
    icon: str
    text: str
    wind360: str
    windDir: str
    windScale: str
    windSpeed: str
    humidity: str
    precip: str
    pressure: str
    vis: str
    cloud: str = None
    dew: str = None
    refer: Dict[str, List[str,]] = {'sources': None, 'license': None}


class WeatherNow(BaseModel):
    code: str
    updateTime: str
    fxLink: str
    now: 'NOW'
