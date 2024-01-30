from typing import List, Dict

from pydantic import BaseModel


class Location(BaseModel):
    name: str
    id: str
    lat: str
    lon: str
    adm2: str
    adm1: str
    country: str
    tz: str
    utcOffset: str
    isDst: str
    type: str
    rank: str
    fxLink: str


class CityLookup(BaseModel):
    code: str
    location: List['Location'] = list()
    refer: Dict[str, List[str,]] = {'sources': None, 'license': None}


class CityTop(BaseModel):
    code: str
    topCityList: List['Location'] = list()
    refer: Dict[str, List[str,]] = {'sources': None, 'license': None}


class PoiLookup(BaseModel):
    code: str
    poi: List['Location'] = list()
    refer: Dict[str, List[str,]] = {'sources': None, 'license': None}


PoiRange = PoiLookup
