from typing import Any
from pydantic import BaseModel


class BaseSeg(BaseModel):
    type: str = "Segment"
    data: dict[str, Any]


class Text(BaseSeg):
    content: str


class Image(BaseSeg):
    url: str
