"""Set the integration up in a real Home Assistant with a fake portal."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.canal_de_isabel_ii.api import AuthError, PortalData
from custom_components.canal_de_isabel_ii.const import DOMAIN, SESSION_OK
from custom_components.canal_de_isabel_ii.csv_parser import Reading
from custom_components.canal_de_isabel_ii.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.canal_de_isabel_ii.meter_parser import MeterSummary

CONTRACT = "999000001"
STATISTIC_ID = f"{DOMAIN}:consumption_{CONTRACT}"
T0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def readings(first_hour, liters):
    return [
        Reading(
            contract=CONTRACT,
            start=T0 + timedelta(hours=first_hour + offset),
            liters=value,
            label=f"hour {first_hour + offset}",
            meter="Y20HK1",
        )
        for offset, value in enumerate(liters)
    ]


METER = MeterSummary(reading_m3=56.735, read_at=None, meter="Y20HK1", address="", raw="56,735m³")


class FakePortal:
    """Stands in for the portal client. Class attributes steer every instance."""

    data = PortalData(readings=[], meter=None)
    valid_sessions = {"good", "better"}

    def __init__(self, jsessionid):
        self.jsessionid = jsessionid

    def check_auth(self):
        return self.jsessionid in self.valid_sessions

    def probe(self):
        return SESSION_OK, None

    def get_consumption_data(self):
        if self.jsessionid not in self.valid_sessions:
            raise AuthError("Authentication failed: Redirected to login page")
        return self.data


@pytest.fixture
def portal():
    FakePortal.data = PortalData(readings=readings(0, [10, 20, 30]), meter=METER)
    with patch("custom_components.canal_de_isabel_ii.CanalIsabelIIAPI", FakePortal):
        yield FakePortal


async def setup_entry(hass, jsessionid="good"):
    entry = MockConfigEntry(domain=DOMAIN, data={"jsessionid": jsessionid})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    return entry


async def stored_statistics(hass):
    await async_wait_recording_done(hass)
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        T0 - timedelta(days=1),
        None,
        {STATISTIC_ID},
        "hour",
        None,
        {"state", "sum"},
    )
    return [(row["state"], row["sum"]) for row in result.get(STATISTIC_ID, [])]


async def test_setup_imports_statistics_and_creates_sensors(recorder_mock, hass, portal):
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]

    consumption = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_consumption")
    assert float(consumption.state) == 30.0
    assert consumption.attributes["statistic_id"] == STATISTIC_ID

    meter = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_meter_reading")
    assert float(meter.state) == 56.735


async def test_overlapping_refresh_continues_the_series(recorder_mock, hass, portal):
    entry = await setup_entry(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # The next download has slid forward: hours 1-4 instead of 0-2.
    portal.data = PortalData(readings=readings(1, [20, 30, 40, 50]), meter=None)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert await stored_statistics(hass) == [
        (10.0, 10.0),
        (20.0, 30.0),
        (30.0, 60.0),
        (40.0, 100.0),
        (50.0, 150.0),
    ]
    # The meter sensor keeps its last reading when a fetch has none.
    meter = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_meter_reading")
    assert float(meter.state) == 56.735


async def test_old_total_entity_is_removed(recorder_mock, hass, portal):
    registry = er.async_get(hass)
    old = registry.async_get_or_create("sensor", DOMAIN, f"canal_ii_total_{CONTRACT}")
    await setup_entry(hass)
    assert registry.async_get(old.entity_id) is None


async def test_rejected_session_asks_for_reauth(recorder_mock, hass, portal):
    entry = await setup_entry(hass, jsessionid="dead")
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["sessions"][-1]["failed_at"] is not None
    assert "dead" not in str(diagnostics)


async def test_set_session_replaces_a_dead_session(recorder_mock, hass, portal):
    entry = await setup_entry(hass, jsessionid="dead")
    assert entry.state is ConfigEntryState.SETUP_ERROR

    await hass.services.async_call(DOMAIN, "set_session", {"jsessionid": "good"}, blocking=True)
    await hass.async_block_till_done()

    assert entry.data["jsessionid"] == "good"
    assert entry.state is ConfigEntryState.LOADED
    assert not hass.config_entries.flow.async_progress()
    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]


async def test_set_session_rejects_an_invalid_cookie(recorder_mock, hass, portal):
    entry = await setup_entry(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_session", {"jsessionid": "bogus"}, blocking=True)
    assert entry.data["jsessionid"] == "good"
