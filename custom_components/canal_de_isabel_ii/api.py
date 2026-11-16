"""API Client for Canal de Isabel II."""
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from typing import List, Optional, Tuple
from .const import (
    BASE_URL,
    CONSUMPTION_URL,
    SESSION_ERROR,
    SESSION_EXPIRED,
    SESSION_OK,
)
from .csv_parser import PORTAL_TZ, Reading, decode_csv, parse_csv
from .meter_parser import MeterSummary, parse_meter_summary

_LOGGER = logging.getLogger(__name__)

# The portal's server sends its own certificate without the intermediate one
# that links it to a trusted root. Browsers fetch the missing piece on their
# own; Python does not, so the intermediate certificates are shipped here.
# They are loaded as trusted certificates of their own: a chain that reaches
# one of them is accepted without going on to the root.
_CERTS_DIR = Path(__file__).parent / "certs"


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    context = create_urllib3_context()
    for cert in sorted(_CERTS_DIR.glob("*.pem")):
        context.load_verify_locations(cafile=str(cert))
    return context


class _PortalAdapter(HTTPAdapter):
    """HTTPS adapter that knows the portal's intermediate certificates."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _ssl_context()
        return super().init_poolmanager(*args, **kwargs)


class PortalError(Exception):
    """The portal could not be read."""


class AuthError(PortalError):
    """The portal did not accept the session."""


@dataclass(frozen=True)
class PortalData:
    """Everything read from the portal in one fetch."""

    readings: List[Reading]
    meter: Optional[MeterSummary]
    # False when a date range was asked for but the page's date fields were
    # not found, so only the portal's default range was read.
    range_applied: bool = True

class CanalIsabelIIAPI:
    """API Client for Canal de Isabel II."""

    def __init__(self, jsessionid: str) -> None:
        """Initialize the API client."""
        self._jsessionid = jsessionid
        self._session = requests.Session()
        self._adapter_mounted = False
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        })
        # Set the session cookie
        self._session.cookies.set('JSESSIONID', self._jsessionid, domain='oficinavirtual.canaldeisabelsegunda.es')

    @property
    def _http(self) -> requests.Session:
        """The session, with the HTTPS adapter mounted on first use.

        Mounting reads certificate files, so it must not happen in __init__,
        which Home Assistant calls from the event loop.
        """
        if not self._adapter_mounted:
            self._session.mount(BASE_URL, _PortalAdapter())
            self._adapter_mounted = True
        return self._session

    def probe(self) -> Tuple[str, Optional[str]]:
        """Check the session against the consumption page.

        Returns (state, detail). SESSION_ERROR means the portal could not be
        reached or failed, which says nothing about the session itself.
        """
        try:
            response = self._http.get(CONSUMPTION_URL, timeout=30, allow_redirects=False)
        except requests.RequestException as err:
            return SESSION_ERROR, f"network error: {err}"

        if response.status_code == 200 and "export-csv" in response.text:
            return SESSION_OK, None

        detail = f"HTTP {response.status_code}"
        # Drop the query and any ;jsessionid suffix: only the path is useful.
        location = response.headers.get("Location", "").split("?")[0].split(";")[0]
        if location:
            detail += f" -> {location}"
        elif response.status_code == 200:
            detail += " without the CSV export link"

        # Only a redirect to the login page (or a plain refusal) says the
        # session is over. Anything else, such as a maintenance page or an
        # error, says nothing about the session.
        if response.status_code in (401, 403) or (
            300 <= response.status_code < 400 and "login" in location.lower()
        ):
            return SESSION_EXPIRED, detail
        return SESSION_ERROR, detail

    def get_consumption_data(self, days: Optional[int] = None) -> PortalData:
        """Fetch the hourly consumption CSV and the meter summary.

        days is how far back to ask, counted from today. Without it the
        portal's own default range is used (the last day with data).

        Raises AuthError if the session is not accepted and PortalError for
        anything else that stops the data from being read.
        """
        try:
            return self._fetch_consumption_data(days)
        except requests.RequestException as err:
            raise PortalError(f"Error talking to the portal: {err}") from err

    def _fetch_consumption_data(self, days: Optional[int]) -> PortalData:
        # 1. Get the consumption page to find the dynamic CSV link and form data
        response = self._http.get(CONSUMPTION_URL, timeout=30, allow_redirects=True)

        if response.status_code in (401, 403):
            raise AuthError(f"Authentication failed: Status {response.status_code}")
        if "login" in response.url or "inicio" in response.url:
            raise AuthError("Authentication failed: Redirected to login page")
        if response.status_code != 200:
            raise PortalError(f"Consumption page returned HTTP {response.status_code}")

        page_html = response.text
        soup = BeautifulSoup(page_html, 'html.parser')
        range_applied = True

        # 2. Switch to Hourly Resolution
        resolution_select = soup.find("select", id="selectPeriodicidad")
        form = resolution_select.find_parent("form") if resolution_select else None
        select_name = resolution_select.get("name") if resolution_select else None
        if select_name and form:
            data = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    data[name] = inp.get("value", "")

            # Handle contract selection if present (preserve selection)
            contract_select = soup.find("select", id="contratosSelect")
            if contract_select:
                selected_opt = contract_select.find("option", selected=True) or contract_select.find("option")
                if selected_opt:
                    data[contract_select.get("name")] = selected_opt["value"]

            data[select_name] = "Horaria"

            if days is not None:
                range_applied = False
                today = datetime.now(PORTAL_TZ).date()
                date_from = form.find("input", id="fechaDesde1")
                date_to = form.find("input", id="fechaHasta1")
                if date_from and date_to and date_from.get("name") and date_to.get("name"):
                    data[date_from["name"]] = (today - timedelta(days=days)).isoformat()
                    data[date_to["name"]] = today.isoformat()
                    range_applied = True
                else:
                    _LOGGER.warning(
                        "Date range fields not found on the consumption page; "
                        "only the portal's default range will be read"
                    )

            _LOGGER.debug("Switching to Hourly resolution...")
            action = urljoin(response.url, form.get("action") or "")
            post_response = self._http.post(action, data=data, timeout=30)
            if "login" in post_response.url:
                raise AuthError("Authentication failed: Redirected to login page")
            if post_response.status_code != 200:
                raise PortalError(
                    f"Asking for hourly data returned HTTP {post_response.status_code}"
                )
            page_html = post_response.text
            soup = BeautifulSoup(page_html, 'html.parser')

        # 3. Find CSV Link
        # The page links the same export as CSV and as XLSX.
        csv_link_tag = soup.find(
            'a', href=lambda x: x and 'export-csv' in x and 'fileFormat=CSV' in x
        ) or soup.find('a', href=lambda x: x and 'export-csv' in x)
        if not csv_link_tag:
            title = soup.title.string.strip() if soup.title and soup.title.string else "No Title"
            raise PortalError(
                f"No CSV download link on the consumption page (title: {title}). "
                "The contract may not have remote reading."
            )

        csv_url = csv_link_tag['href']
        if not csv_url.startswith('http'):
            csv_url = BASE_URL + csv_url

        # 4. Download and parse the CSV
        csv_response = self._http.get(csv_url, timeout=60)
        if "login" in csv_response.url:
            raise AuthError("Authentication failed: Redirected to login page")
        csv_response.raise_for_status()
        csv_text = decode_csv(csv_response.content)
        if csv_text.lstrip()[:1] == "<":
            raise PortalError("The CSV download returned a web page instead of data")
        readings = parse_csv(csv_text)
        _LOGGER.debug("Downloaded %s hourly readings", len(readings))

        # 5. The absolute meter reading shown above the chart
        meter = parse_meter_summary(page_html)
        if meter is None:
            _LOGGER.debug("No meter summary found on the consumption page")

        return PortalData(readings=readings, meter=meter, range_applied=range_applied)
