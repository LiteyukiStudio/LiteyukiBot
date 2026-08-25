"""Basic message segment models retained for v6 imports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BaseSeg(BaseModel):
    """Represent the validated base seg contract."""
    type: str = "Segment"
    data: dict[str, Any]


class Text(BaseSeg):
    """Represent the text contract."""
    content: str


class Image(BaseSeg):
    """Represent the image contract."""
    url: str


__all__ = ["BaseSeg", "Image", "Text"]
