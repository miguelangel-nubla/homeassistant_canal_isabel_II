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
    assert row.start == utc(2026, 4, 22, 0)  # the hour that ends at 03:00 CEST
    assert row.label == "22/04/2026 03"
    assert (row.meter, row.address, row.frequency) == ("Y20HK1", "C/ Ejemplo", "Horaria")


def test_winter_time_offset():
    rows = parse_csv(HEADER + "1,P,M,A,Horaria,15/01/2026 03,5\n")
    assert rows[0].start == utc(2026, 1, 15, 1)  # the hour that ends at 03:00 CET


def test_the_label_names_the_end_of_its_hour():
    # The newest row the portal publishes: the last hour of the day before.
    rows = parse_csv(HEADER + "1,P,M,A,Horaria,16/11/2026 00,74.21\n")
    assert rows[0].start == utc(2026, 11, 15, 22)  # 23:00 CET on the 15th


def test_the_hour_is_taken_off_in_real_time_when_the_clocks_change():
    # 29/03/2026: the clocks go from 02:00 to 03:00. The hour that ends at
    # 03:00 CEST started at 01:00 CET, an hour of real time before.
    spring = parse_csv(HEADER + "1,P,M,A,Horaria,29/03/2026 01,1\n1,P,M,A,Horaria,29/03/2026 03,2\n")
    assert [row.start for row in spring] == [utc(2026, 3, 28, 23), utc(2026, 3, 29, 0)]
    # 25/10/2026: 03:00 CEST becomes 02:00 CET. The hour that ends at 03:00
    # CET started at 02:00 CET.
    autumn = parse_csv(HEADER + "1,P,M,A,Horaria,25/10/2026 03,3\n")
    assert autumn[0].start == utc(2026, 10, 25, 1)


def test_hour_label_as_start_is_still_understood(monkeypatch):
    monkeypatch.setattr(csv_parser, "HOUR_LABEL_IS_END", False)
    rows = parse_csv(HEADER + "1,P,M,A,Horaria,22/04/2026 00,5\n")
    assert rows[0].start == utc(2026, 4, 21, 22)  # 00:00 CEST


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
    assert totals["1"] == {utc(2026, 4, 22, 0): 5.0, utc(2026, 4, 22, 1): 6.0}
    assert totals["2"] == {utc(2026, 4, 22, 0): 9.0}


def test_hourly_totals_adds_rows_on_the_same_hour():
    text = HEADER + "1,P,M,A,Horaria,22/04/2026 03,5\n1,P,M,A,Horaria,22/04/2026 03,2\n"
    assert hourly_totals(parse_csv(text))["1"] == {utc(2026, 4, 22, 0): 7.0}
