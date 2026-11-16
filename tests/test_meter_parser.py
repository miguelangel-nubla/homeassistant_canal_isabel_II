from datetime import datetime
from zoneinfo import ZoneInfo

from meter_parser import parse_meter_summary, parse_reading_m3

PAGE = """
<html><body><ul class="datos">
  <li><h5 class="titulo">Dirección suministro</h5><h5 class="dato dato1">C/ Ejemplo 1</h5></li>
  <li><h5 class="titulo">Contador</h5><h5 class="dato dato1">Y20HK123456</h5></li>
  <li><h5 class="titulo">Última lectura</h5><h5 class="dato minusculas">56,735<span>m³</span></h5></li>
  <li><h5 class="titulo">Fecha y hora lectura</h5><h5 class="dato dato1">22/04/2026 03:00</h5></li>
</ul>
<ul><li><a href="/x">menu</a></li></ul></body></html>
"""


def test_reading_value_formats():
    assert parse_reading_m3("56,735m³") == 56.735
    assert parse_reading_m3("1.056,735 m3") == 1056.735
    assert parse_reading_m3("57 m³") == 57.0
    assert parse_reading_m3("") is None
    assert parse_reading_m3("sin datos") is None


def test_summary_is_extracted():
    summary = parse_meter_summary(PAGE)
    assert summary.reading_m3 == 56.735
    assert summary.raw == "56,735m³"
    assert summary.meter == "Y20HK123456"
    assert summary.address == "C/ Ejemplo 1"
    assert summary.read_at == datetime(2026, 4, 22, 3, 0, tzinfo=ZoneInfo("Europe/Madrid"))


def test_missing_date_still_gives_a_reading():
    page = PAGE.replace("22/04/2026 03:00", "pendiente")
    summary = parse_meter_summary(page)
    assert summary.reading_m3 == 56.735
    assert summary.read_at is None


def test_page_without_summary():
    assert parse_meter_summary("") is None
    assert parse_meter_summary("<html><body><form id='login'></form></body></html>") is None


def test_thousands_separator_without_decimals():
    assert parse_reading_m3("1.234m³") == 1234.0
    assert parse_reading_m3("1.234,565m³") == 1234.565
    assert parse_reading_m3("56.7m³") == 56.7
