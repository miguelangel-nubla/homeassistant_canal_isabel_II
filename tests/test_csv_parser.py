from datetime import datetime, timezone

import csv_parser
from csv_parser import decode_csv, hourly_totals, parse_csv

HEADER = "Contrato,Periodo,Contador,Dirección,Frecuencia,Fecha/Hora,Consumo (litros)\n"


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_parses_a_row_as_madrid_time():
    rows = parse_csv(HEADER + "999000001,Facturado,Y20HK1,C/ Ejemplo,Horaria,22/04/2026 03,12\n")
    assert len(rows) == 1
    row = rows[0]
    assert row.contract == "999000001"
    assert row.liters == 12.0
    assert row.start == utc(2026, 4, 22, 1)  # 03:00 CEST
    assert row.label == "22/04/2026 03"
    assert (row.meter, row.address, row.frequency) == ("Y20HK1", "C/ Ejemplo", "Horaria")


def test_winter_time_offset():
    rows = parse_csv(HEADER + "1,P,M,A,Horaria,15/01/2026 03,5\n")
    assert rows[0].start == utc(2026, 1, 15, 2)  # 03:00 CET


def test_hour_label_as_end_shifts_one_hour_back(monkeypatch):
    monkeypatch.setattr(csv_parser, "HOUR_LABEL_IS_END", True)
    rows = parse_csv(HEADER + "1,P,M,A,Horaria,22/04/2026 00,5\n")
    assert rows[0].start == utc(2026, 4, 21, 21)  # 23:00 CEST the day before


def test_semicolon_delimiter_and_decimal_comma():
    text = HEADER.replace(",", ";") + "1;P;M;A;Horaria;22/04/2026 03;12,5\n"
    assert parse_csv(text)[0].liters == 12.5


def test_quoted_decimal_comma_with_comma_delimiter():
    assert parse_csv(HEADER + '1,P,M,A,Horaria,22/04/2026 03,"12,5"\n')[0].liters == 12.5


def test_bad_rows_are_skipped():
    text = HEADER + (
        "1,P,M,A,Horaria,not a date,5\n"
        "1,P,M,A,Horaria,22/04/2026 03,abc\n"
        "1,P,M,A,Horaria,22/04/2026 04,\n"
        ",P,M,A,Horaria,22/04/2026 05,5\n"
        "1,P,M,A,Horaria,22/04/2026 06,7\n"
    )
    rows = parse_csv(text)
    assert [row.liters for row in rows] == [7.0]


def test_empty_input():
    assert parse_csv("") == []
    assert parse_csv(HEADER) == []


def test_decode_strips_bom_and_falls_back_to_latin1():
    assert decode_csv(b"\xef\xbb\xbfContrato").startswith("Contrato")
    assert decode_csv("Dirección".encode("latin-1")) == "Dirección"
    with_bom = decode_csv(("﻿" + HEADER + "1,P,M,A,Horaria,22/04/2026 03,5\n").encode("utf-8"))
    assert parse_csv(with_bom)[0].contract == "1"


def test_hourly_totals_groups_by_contract():
    text = HEADER + (
        "1,P,M,A,Horaria,22/04/2026 03,5\n"
        "1,P,M,A,Horaria,22/04/2026 04,6\n"
        "2,P,N,B,Horaria,22/04/2026 03,9\n"
    )
    totals = hourly_totals(parse_csv(text))
    assert totals["1"] == {utc(2026, 4, 22, 1): 5.0, utc(2026, 4, 22, 2): 6.0}
    assert totals["2"] == {utc(2026, 4, 22, 1): 9.0}


def test_hourly_totals_adds_rows_on_the_same_hour():
    text = HEADER + "1,P,M,A,Horaria,22/04/2026 03,5\n1,P,M,A,Horaria,22/04/2026 03,2\n"
    assert hourly_totals(parse_csv(text))["1"] == {utc(2026, 4, 22, 1): 7.0}
