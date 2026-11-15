"""Parser for the portal's hourly consumption CSV.

Pure Python on purpose (no Home Assistant, no relative imports) so it can be
tested on its own.

The CSV looks like:

    Contrato,Periodo,Contador,Dirección,Frecuencia,Fecha/Hora,Consumo (litros)
    999000001,Facturado,Y20HK123456,C/ Ejemplo,Horaria,22/04/2026 03,12

"Fecha/Hora" is Madrid wall-clock time with hour resolution.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Dict, List
from zoneinfo import ZoneInfo

PORTAL_TZ = ZoneInfo("Europe/Madrid")

# Whether the hour in "Fecha/Hora" names the end of the measured hour (True)
# or its start (False). Checked against the portal 2026-11: its daily totals
# equal the sum of that day's labels 00 to 23 (36 days out of 36), so a label
# belongs to the day and hour it names.
HOUR_LABEL_IS_END = False

TIME_FORMAT = "%d/%m/%Y %H"


@dataclass(frozen=True)
class Reading:
    """One hourly consumption row."""

    contract: str
    start: datetime  # start of the measured hour, timezone-aware UTC
    liters: float
    label: str  # "Fecha/Hora" exactly as the portal wrote it
    meter: str = ""
    address: str = ""
    period: str = ""
    frequency: str = ""


def decode_csv(content: bytes) -> str:
    """Decode the downloaded CSV, tolerating a BOM and legacy encodings."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _delimiter(text: str) -> str:
    header = text.lstrip().split("\n", 1)[0]
    return ";" if header.count(";") > header.count(",") else ","


def _parse_start(label: str) -> datetime:
    local = datetime.strptime(label, TIME_FORMAT)
    if HOUR_LABEL_IS_END:
        local -= timedelta(hours=1)
    return local.replace(tzinfo=PORTAL_TZ).astimezone(timezone.utc)


def parse_csv(text: str) -> List[Reading]:
    """Parse the CSV text. Rows that cannot be read are skipped."""
    if not text or not text.strip():
        return []
    readings: List[Reading] = []
    reader = csv.DictReader(StringIO(text), delimiter=_delimiter(text))
    for row in reader:
        label = (row.get("Fecha/Hora") or "").strip()
        contract = (row.get("Contrato") or "").strip()
        try:
            start = _parse_start(label)
            liters = float((row.get("Consumo (litros)") or "").strip().replace(",", "."))
        except ValueError:
            continue
        if not contract:
            continue
        readings.append(
            Reading(
                contract=contract,
                start=start,
                liters=liters,
                label=label,
                meter=(row.get("Contador") or "").strip(),
                address=(row.get("Dirección") or "").strip(),
                period=(row.get("Periodo") or "").strip(),
                frequency=(row.get("Frecuencia") or "").strip(),
            )
        )
    return readings


def hourly_totals(readings: List[Reading]) -> Dict[str, Dict[datetime, float]]:
    """Group readings as {contract: {hour start: liters}}.

    Rows that land on the same hour are added together. That only happens on
    the autumn clock change, when the same wall-clock hour occurs twice.
    """
    totals: Dict[str, Dict[datetime, float]] = {}
    for reading in readings:
        hours = totals.setdefault(reading.contract, {})
        hours[reading.start] = hours.get(reading.start, 0.0) + reading.liters
    return totals
