"""The portal client's requests, against a canned consumption page."""
from datetime import date, timedelta

import pytest

from custom_components.canal_de_isabel_ii.api import AuthError, CanalIsabelIIAPI, PortalError
from custom_components.canal_de_isabel_ii.const import (
    SESSION_ERROR,
    SESSION_EXPIRED,
    SESSION_OK,
)

NS = "_ovirtelelecturamodule_INSTANCE_abc_"
PAGE = f"""
<html><body>
<form action="https://portal.invalid/post" method="post">
  <input type="date" id="fechaDesde1" name="{NS}fechaDesde" value="2026-11-14">
  <input type="date" id="fechaHasta1" name="{NS}fechaHasta" value="2026-11-14">
  <select id="selectPeriodicidad" name="{NS}periodicidad">
    <option value="Horaria">Horaria</option><option value="Diaria" selected>Diaria</option>
  </select>
  <select id="contratosSelect" name="{NS}contratosFiltro"><option value="999000001" selected>x</option></select>
</form>
<a href="/group/ovir/consumo?p_p_resource_id=export-csv&{NS}fileFormat=XLSX">xlsx</a>
<a href="/group/ovir/consumo?p_p_resource_id=export-csv&{NS}fileFormat=CSV">csv</a>
</body></html>
"""
CSV = (
    '"Contrato","Dirección","Contador","Frecuencia","Periodo","Fecha/Hora","Consumo (litros)"\n'
    '"999000001","Calle","Y20HK1","Horaria","P","14/11/2026 23","5,09"\n'
)


class Response:
    def __init__(self, text="", url="https://portal.invalid/group/ovir/consumo"):
        self.status_code = 200
        self.text = text
        self.content = text.encode()
        self.url = url

    def raise_for_status(self):
        pass


class Session:
    def __init__(self):
        self.posted = None
        self.fetched = []

    def get(self, url, **kwargs):
        self.fetched.append(url)
        return Response(CSV if "export-csv" in url else PAGE)

    def post(self, url, data=None, **kwargs):
        self.posted = data
        return Response(PAGE)


def client():
    api = CanalIsabelIIAPI("cookie")
    api._session = Session()
    api._adapter_mounted = True
    return api


def test_requested_days_set_the_date_range():
    api = client()
    data = api.get_consumption_data(30)

    posted = api._session.posted
    assert posted[f"{NS}periodicidad"] == "Horaria"
    assert posted[f"{NS}contratosFiltro"] == "999000001"
    date_from = date.fromisoformat(posted[f"{NS}fechaDesde"])
    date_to = date.fromisoformat(posted[f"{NS}fechaHasta"])
    assert date_to - date_from == timedelta(days=30)
    assert abs((date.today() - date_to).days) <= 1
    assert data.readings[0].liters == 5.09


def test_without_days_the_portal_default_range_is_kept():
    api = client()
    api.get_consumption_data()

    assert api._session.posted[f"{NS}fechaDesde"] == "2026-11-14"


def test_the_csv_link_is_preferred_over_xlsx():
    api = client()
    api.get_consumption_data(30)

    assert api._session.fetched[-1].endswith("fileFormat=CSV")


class Probe:
    """A session whose only answer is the given response."""

    def __init__(self, status, location="", text=""):
        self.response = Response(text)
        self.response.status_code = status
        self.response.headers = {"Location": location} if location else {}

    def get(self, url, **kwargs):
        return self.response


def probe(status, location="", text=""):
    api = CanalIsabelIIAPI("cookie")
    api._session = Probe(status, location, text)
    api._adapter_mounted = True
    return api.probe()[0]


def test_only_a_login_redirect_or_refusal_ends_the_session():
    assert probe(200, text="...export-csv...") == SESSION_OK
    assert probe(302, "https://portal.invalid/c/portal/login?x=1") == SESSION_EXPIRED
    assert probe(403) == SESSION_EXPIRED
    # None of these say anything about the session.
    assert probe(302, "https://portal.invalid/mantenimiento") == SESSION_ERROR
    assert probe(200, text="<html>otra cosa</html>") == SESSION_ERROR
    assert probe(429) == SESSION_ERROR
    assert probe(503) == SESSION_ERROR


def test_a_csv_that_is_a_web_page_is_an_error():
    api = client()
    api._session.get = lambda url, **kwargs: Response(
        "<html>error</html>" if "export-csv" in url else PAGE
    )
    with pytest.raises(PortalError):
        api.get_consumption_data(30)


def test_a_csv_request_sent_to_the_login_page_is_an_auth_error():
    api = client()
    api._session.get = lambda url, **kwargs: (
        Response("<html>", url="https://portal.invalid/c/portal/login")
        if "export-csv" in url
        else Response(PAGE)
    )
    with pytest.raises(AuthError):
        api.get_consumption_data(30)
