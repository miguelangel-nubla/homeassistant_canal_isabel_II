"""Extract the absolute meter reading from the consumption page.

No Home Assistant and no relative imports, so it can be tested on its own.

The page shows a row of cards above the chart, each an <li> holding a title
and a value:

    <li> <h5 class="titulo">Contador</h5>       <h5 class="dato dato1">Y20HK123456</h5> </li>
    <li> <h5 class="titulo">Última lectura</h5> <h5 class="dato minusculas">56,735m³</h5> </li>
    <li> <h5 class="titulo">Fecha y hora lectura</h5> <h5 class="dato dato1">22/04/2026 03:00</h5> </li>

This is the figure that matches the bill, unlike the sum of hourly rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

PORTAL_TZ = ZoneInfo("Europe/Madrid")

_VALUE_RE = re.compile(r"([\d.,]+)\s*m", re.IGNORECASE)


@dataclass(frozen=True)
class MeterSummary:
    """The meter card values shown on the consumption page."""

    reading_m3: float
    read_at: Optional[datetime]  # timezone-aware
    meter: str
    address: str
    raw: str  # reading exactly as shown, e.g. "56,735m³"


def parse_reading_m3(raw: str) -> Optional[float]:
    """Turn "56,735m³" (Spanish decimal comma) into 56.735."""
    match = _VALUE_RE.search(raw or "")
    if not match:
        return None
    token = match.group(1)
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def _parse_read_at(raw: str) -> Optional[datetime]:
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M").replace(tzinfo=PORTAL_TZ)
    except ValueError:
        return None


def _is_title(css_class: Optional[str]) -> bool:
    return bool(css_class) and "titulo" in css_class


def parse_meter_summary(html: str) -> Optional[MeterSummary]:
    """Return the meter summary, or None if the page does not show one."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    fields: Dict[str, str] = {}
    for item in soup.find_all("li"):
        title_tag = item.find("h5", class_=_is_title)
        value_tag = item.find("h5", class_="dato")
        if not title_tag or not value_tag:
            continue
        title = " ".join(title_tag.get_text().split()).lower()
        value = " ".join(value_tag.get_text().split())
        if not value:
            continue
        if "ltima lectura" in title:
            fields["raw"] = value
        elif "fecha" in title and "lectura" in title:
            fields["read_at"] = value
        elif "contador" in title:
            fields["meter"] = value
        elif "direcci" in title:
            fields["address"] = value

    reading = parse_reading_m3(fields.get("raw", ""))
    if reading is None:
        return None
    return MeterSummary(
        reading_m3=reading,
        read_at=_parse_read_at(fields.get("read_at", "")),
        meter=fields.get("meter", ""),
        address=fields.get("address", ""),
        raw=fields["raw"],
    )
