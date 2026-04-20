from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None
    summary: Optional[str] = None


@dataclass
class Company:
    name: str
    source: str
    rank: Optional[int] = None
    year: Optional[int] = None
    url: Optional[str] = None

