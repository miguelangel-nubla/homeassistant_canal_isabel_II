"""API Client for Canal de Isabel II."""
import logging
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional, Tuple
from .const import (
    BASE_URL,
    CONSUMPTION_URL,
    SESSION_ERROR,
    SESSION_EXPIRED,
    SESSION_OK,
)
from .csv_parser import Reading, decode_csv, parse_csv
from .meter_parser import MeterSummary, parse_meter_summary

_LOGGER = logging.getLogger(__name__)

class PortalError(Exception):
    """The portal could not be read."""


class AuthError(PortalError):
    """The portal did not accept the session."""


@dataclass(frozen=True)
class PortalData:
    """Everything read from the portal in one fetch."""

    readings: List[Reading]
    meter: Optional[MeterSummary]

class CanalIsabelIIAPI:
    """API Client for Canal de Isabel II."""

    def __init__(self, jsessionid: str) -> None:
        """Initialize the API client."""
        self._jsessionid = jsessionid
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        })
        # Set the session cookie
        self._session.cookies.set('JSESSIONID', self._jsessionid, domain='oficinavirtual.canaldeisabelsegunda.es')

    def probe(self) -> Tuple[str, Optional[str]]:
        """Check the session against the consumption page.

        Returns (state, detail). SESSION_ERROR means the portal could not be
        reached or failed, which says nothing about the session itself.
        """
        try:
            response = self._session.get(CONSUMPTION_URL, timeout=30, allow_redirects=False)
        except requests.RequestException as err:
            return SESSION_ERROR, f"network error: {err}"

        if response.status_code == 200 and "export-csv" in response.text:
            return SESSION_OK, None
        if response.status_code >= 500:
            return SESSION_ERROR, f"HTTP {response.status_code}"

        detail = f"HTTP {response.status_code}"
        # Drop the query and any ;jsessionid suffix: only the path is useful.
        location = response.headers.get("Location", "").split("?")[0].split(";")[0]
        if location:
            detail += f" -> {location}"
        elif response.status_code == 200:
            detail += " without the CSV export link"
        return SESSION_EXPIRED, detail

    def check_auth(self) -> bool:
        """Check if the session is valid."""
        state, detail = self.probe()
        if state != SESSION_OK:
            _LOGGER.warning("Auth check failed: %s", detail)
        return state == SESSION_OK

    def get_consumption_data(self) -> PortalData:
        """Fetch the hourly consumption CSV and the meter summary.

        Raises AuthError if the session is not accepted and PortalError for
        anything else that stops the data from being read.
        """
        try:
            return self._fetch_consumption_data()
        except requests.RequestException as err:
            raise PortalError(f"Error talking to the portal: {err}") from err

    def _fetch_consumption_data(self) -> PortalData:
        # 1. Get the consumption page to find the dynamic CSV link and form data
        response = self._session.get(CONSUMPTION_URL, timeout=30, allow_redirects=True)

        if response.status_code in (401, 403):
            raise AuthError(f"Authentication failed: Status {response.status_code}")
        if "login" in response.url or "inicio" in response.url:
            raise AuthError("Authentication failed: Redirected to login page")
        if response.status_code != 200:
            raise PortalError(f"Consumption page returned HTTP {response.status_code}")

        page_html = response.text
        soup = BeautifulSoup(page_html, 'html.parser')

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

            _LOGGER.debug("Switching to Hourly resolution...")
            post_response = self._session.post(form.get("action"), data=data, timeout=30)
            if post_response.status_code == 200:
                page_html = post_response.text
                soup = BeautifulSoup(page_html, 'html.parser')
            else:
                _LOGGER.error("Failed to switch resolution, status: %s", post_response.status_code)

        # 3. Find CSV Link
        csv_link_tag = soup.find('a', href=lambda x: x and 'export-csv' in x)
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
        csv_response = self._session.get(csv_url, timeout=60)
        csv_response.raise_for_status()
        readings = parse_csv(decode_csv(csv_response.content))
        _LOGGER.debug("Downloaded %s hourly readings", len(readings))

        # 5. The absolute meter reading shown above the chart
        meter = parse_meter_summary(page_html)
        if meter is None:
            _LOGGER.debug("No meter summary found on the consumption page")

        return PortalData(readings=readings, meter=meter)
