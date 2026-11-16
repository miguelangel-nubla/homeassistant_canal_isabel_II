"""Set the integration up in a real Home Assistant with a fake portal."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.canal_de_isabel_ii.api import AuthError, PortalData, PortalError
from custom_components.canal_de_isabel_ii.const import (
    DOMAIN,
    HELPER_TIMEOUT,
    HELPER_WATCH_INTERVAL,
    HISTORY_DAYS,
    REFRESH_DAYS,
    SESSION_EXPIRED,
    SESSION_OK,
)
from custom_components.canal_de_isabel_ii.csv_parser import Reading
from custom_components.canal_de_isabel_ii.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.canal_de_isabel_ii.meter_parser import MeterSummary
from custom_components.canal_de_isabel_ii.statistics import async_import_consumption

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

    def probe(self):
        if self.jsessionid not in self.valid_sessions:
            return SESSION_EXPIRED, "HTTP 302 -> /c/portal/login"
        return SESSION_OK, None

    requested_days = []
    broken = False

    def get_consumption_data(self, days=None):
        FakePortal.requested_days.append(days)
        if FakePortal.broken:
            raise PortalError("No CSV download link on the consumption page")
        if self.jsessionid not in self.valid_sessions:
            raise AuthError("Authentication failed: Redirected to login page")
        return self.data


@pytest.fixture
def portal():
    FakePortal.data = PortalData(readings=readings(0, [10, 20, 30]), meter=METER)
    FakePortal.requested_days = []
    FakePortal.broken = False
    with patch("custom_components.canal_de_isabel_ii.CanalIsabelIIAPI", FakePortal):
        yield FakePortal


ACCOUNT = {
    "document": "X1234567L",
    "password": "secret",
    "profile": "particular",
    "credentials_set_at": "2026-11-16T00:00:00+00:00",
}


async def setup_entry(hass, jsessionid="good"):
    """An entry with its account and, unless empty, a session delivered earlier."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={**ACCOUNT, "jsessionid": jsessionid})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    return entry


async def helper_asks(hass, **data):
    """What the session helper does every minute."""
    answer = await hass.services.async_call(
        DOMAIN, "session_request", data, blocking=True, return_response=True
    )
    return answer["requests"]


def issues(hass):
    return {issue.issue_id: issue for issue in ir.async_get(hass).issues.values() if issue.domain == DOMAIN}


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


async def test_setup_imports_statistics_and_creates_sensors(
    recorder_mock, hass, portal, entity_registry_enabled_by_default
):
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]

    consumption = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_last_hour_s_consumption")
    assert float(consumption.state) == 30.0
    assert consumption.attributes["statistic_id"] == STATISTIC_ID

    meter = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_meter_reading")
    assert float(meter.state) == 56.735


async def test_the_sensors_describe_the_last_full_day(recorder_mock, hass, portal):
    # T0 is 02:00 in Madrid. Three full days from midnight, the last two
    # with water running every hour, then two hours of a fourth.
    first_day = [0, 0, 0, 0, 0, 0, 12, 40] + [10] * 16
    wet_days = [1.5] * 48
    fourth_day = [1.5] * 2
    portal.data = PortalData(readings=readings(-2, first_day + wet_days + fourth_day), meter=METER)
    await setup_entry(hass)
    prefix = f"canal_de_isabel_ii_{CONTRACT}"

    last_day = hass.states.get(f"sensor.{prefix}_last_day_s_consumption")
    assert float(last_day.state) == 36.0
    assert last_day.attributes["date"] == "2026-04-03"
    assert float(hass.states.get(f"sensor.{prefix}_last_day_s_minimum_flow").state) == 1.5
    assert hass.states.get(f"sensor.{prefix}_data_until").state == "2026-04-04T00:00:00+00:00"

    leak = hass.states.get(f"binary_sensor.{prefix}_possible_leak")
    assert leak.state == "on"
    assert leak.attributes["hours_without_pause"] == 68  # since 06:00 of the first day
    # The hourly sensor is off unless someone turns it on.
    assert hass.states.get(f"sensor.{prefix}_last_hour_s_consumption") is None
    assert er.async_get(hass).async_get(f"sensor.{prefix}_last_hour_s_consumption").disabled


async def test_the_leak_check_has_its_own_settings_for_each_contract(recorder_mock, hass, portal):
    # After an hour with nothing, water every hour for four days, but never
    # more than 0.8 L: under the default limit that is a meter at rest.
    portal.data = PortalData(readings=readings(-2, [0] + [0.8] * 100), meter=METER)
    entry = await setup_entry(hass)
    registry = er.async_get(hass)
    leak = f"binary_sensor.canal_de_isabel_ii_{CONTRACT}_possible_leak"
    rest = registry.async_get_entity_id("number", DOMAIN, f"canal_ii_rest_liters_{CONTRACT}")
    hours = registry.async_get_entity_id("number", DOMAIN, f"canal_ii_leak_hours_{CONTRACT}")
    assert float(hass.states.get(rest).state) == 1.0
    assert float(hass.states.get(hours).state) == 48
    assert hass.states.get(leak).state == "off"

    # A household that wants to hear about a trickle that small.
    await hass.services.async_call("number", "set_value", {"entity_id": rest, "value": 0.5}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(leak).state == "on"
    assert hass.states.get(leak).attributes["liters_per_hour_at_rest"] == 0.5

    # ...but only after five days of it.
    await hass.services.async_call("number", "set_value", {"entity_id": hours, "value": 120}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(leak).state == "off"

    # The settings are kept across a restart of the integration.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(rest).state) == 0.5
    assert float(hass.states.get(hours).state) == 120
    assert hass.states.get(leak).state == "off"
    assert hass.states.get(leak).attributes["hours_for_a_leak"] == 120


async def test_each_contract_of_the_account_has_its_own_device(recorder_mock, hass, portal):
    other = "999000002"
    theirs = [
        Reading(contract=other, start=reading.start, liters=reading.liters * 2, label=reading.label, meter="Z99")
        for reading in readings(0, [10, 20, 30])
    ]
    portal.data = PortalData(
        readings=readings(0, [10, 20, 30]) + theirs,
        meter=METER,
        meters={
            CONTRACT: METER,
            other: MeterSummary(reading_m3=7.25, read_at=None, meter="Z99", address="", raw="7,250m³"),
        },
    )
    await setup_entry(hass)

    assert float(hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_meter_reading").state) == 56.735
    assert float(hass.states.get(f"sensor.canal_de_isabel_ii_{other}_meter_reading").state) == 7.25
    assert hass.states.get(f"binary_sensor.canal_de_isabel_ii_{other}_possible_leak") is not None
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, f"canal_ii_rest_liters_{other}")
    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]


async def test_overlapping_refresh_continues_the_series(recorder_mock, hass, portal):
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

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


async def test_first_download_asks_for_the_history_then_a_short_window(recorder_mock, hass, portal):
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert portal.requested_days == [HISTORY_DAYS, REFRESH_DAYS]


async def test_older_history_is_merged_before_existing_rows(recorder_mock, hass, portal):
    # An install that already holds hours 2-4 and then receives hours 0-4.
    portal.data = PortalData(readings=readings(2, [30, 40, 50]), meter=METER)
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    assert await stored_statistics(hass) == [(30.0, 30.0), (40.0, 70.0), (50.0, 120.0)]

    portal.data = PortalData(readings=readings(0, [10, 20, 30, 40, 50]), meter=None)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert await stored_statistics(hass) == [
        (10.0, 10.0),
        (20.0, 30.0),
        (30.0, 60.0),
        (40.0, 100.0),
        (50.0, 150.0),
    ]


async def test_portal_error_at_setup_still_loads_and_recovers(
    recorder_mock, hass, portal, entity_registry_enabled_by_default
):
    portal.broken = True
    entry = await setup_entry(hass)
    # Loaded: the fetch is tried again later and nothing hammers the portal.
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_last_hour_s_consumption") is None

    portal.broken = False
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # The sensors appear with the first data, without a reload.
    consumption = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_last_hour_s_consumption")
    assert float(consumption.state) == 30.0
    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]


async def test_history_is_asked_again_when_the_range_was_not_applied(recorder_mock, hass, portal):
    portal.data = PortalData(readings=readings(0, [10]), meter=None, range_applied=False)
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert portal.requested_days == [HISTORY_DAYS, HISTORY_DAYS]


async def test_imports_in_a_row_do_not_wait_for_the_recorder(recorder_mock, hass, portal):
    # The second import runs before the recorder has written the first.
    await async_import_consumption(hass, CONTRACT, {T0 + timedelta(hours=h): v for h, v in enumerate([10, 20, 30])})
    await async_import_consumption(hass, CONTRACT, {T0 + timedelta(hours=h): v for h, v in ((2, 30), (3, 40))})

    assert await stored_statistics(hass) == [
        (10.0, 10.0),
        (20.0, 30.0),
        (30.0, 60.0),
        (40.0, 100.0),
    ]


async def test_old_total_entity_is_removed(recorder_mock, hass, portal):
    registry = er.async_get(hass)
    old = registry.async_get_or_create("sensor", DOMAIN, f"canal_ii_total_{CONTRACT}")
    await setup_entry(hass)
    assert registry.async_get(old.entity_id) is None


async def test_without_a_session_the_helper_is_asked_for_one(
    recorder_mock, hass, portal, entity_registry_enabled_by_default
):
    entry = await setup_entry(hass, jsessionid="")
    assert entry.state is ConfigEntryState.LOADED
    assert portal.requested_days == []
    assert not hass.config_entries.flow.async_progress()

    assert await helper_asks(hass) == [{"entry_id": entry.entry_id, **ACCOUNT}]

    await hass.services.async_call(
        DOMAIN, "set_session", {"jsessionid": "good", "entry_id": entry.entry_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.data["jsessionid"] == "good"
    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0)]
    consumption = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_last_hour_s_consumption")
    assert float(consumption.state) == 30.0
    # Served: nothing is wanted until the next fetch finds the session gone.
    assert await helper_asks(hass) == []


async def test_an_ended_session_is_replaced_without_bothering_anyone(
    recorder_mock, hass, portal, entity_registry_enabled_by_default
):
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    assert await helper_asks(hass) == []

    # By the next fetch the portal has ended the session, as it always does.
    with patch.object(portal, "valid_sessions", {"better"}):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # The sensors keep their values, nobody is asked to do anything...
        consumption = hass.states.get(f"sensor.canal_de_isabel_ii_{CONTRACT}_last_hour_s_consumption")
        assert float(consumption.state) == 30.0
        assert coordinator.last_update_success
        assert not hass.config_entries.flow.async_progress()
        assert not issues(hass)
        # ...and the helper is asked for a new session.
        assert [request["entry_id"] for request in await helper_asks(hass)] == [entry.entry_id]

        portal.data = PortalData(readings=readings(1, [20, 30, 40]), meter=None)
        await hass.services.async_call(DOMAIN, "set_session", {"jsessionid": "better"}, blocking=True)
        await hass.async_block_till_done()

    assert entry.data["jsessionid"] == "better"
    assert await stored_statistics(hass) == [(10.0, 10.0), (20.0, 30.0), (30.0, 60.0), (40.0, 100.0)]
    assert await helper_asks(hass) == []

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert [bool(session["failed_at"]) for session in diagnostics["sessions"]] == [True, False]
    assert "secret" not in str(diagnostics) and "better" not in str(diagnostics)


async def test_set_session_rejects_an_invalid_cookie(recorder_mock, hass, portal):
    entry = await setup_entry(hass, jsessionid="")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_session", {"jsessionid": "bogus"}, blocking=True)
    assert entry.data["jsessionid"] == ""
    assert len(await helper_asks(hass)) == 1


async def test_a_refused_login_asks_for_the_credentials_again(recorder_mock, hass, portal):
    entry = await setup_entry(hass, jsessionid="")
    await hass.services.async_call(DOMAIN, "report_login", {"result": "failed"}, blocking=True)
    assert issues(hass)[f"login_needs_a_person_{entry.entry_id}"].translation_key == "login_failed"
    await hass.services.async_call(
        DOMAIN,
        "report_login",
        {"entry_id": entry.entry_id, "result": "refused", "detail": "Usuario o contraseña incorrectos"},
        blocking=True,
    )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
    # The notice of the earlier try is gone: it no longer describes the situation.
    assert not issues(hass)
    # The helper is not given the refused credentials again.
    assert await helper_asks(hass) == []

    await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"document": "X1234567L", "password": "right", "profile": "particular"}
    )
    await hass.async_block_till_done()
    requests = await helper_asks(hass)
    assert [request["password"] for request in requests] == ["right"]
    assert requests[0]["credentials_set_at"] != ACCOUNT["credentials_set_at"]


@pytest.mark.parametrize("result", ["challenge", "failed"])
async def test_a_login_that_needs_a_person_is_a_repair_issue(recorder_mock, hass, portal, result):
    entry = await setup_entry(hass, jsessionid="")
    await hass.services.async_call(
        DOMAIN,
        "report_login",
        {
            "entry_id": entry.entry_id,
            "result": result,
            "retry_at": "2026-11-16T12:00:00+00:00",
            "helper_url": "http://helper.example/",
        },
        blocking=True,
    )
    issue = issues(hass)[f"login_needs_a_person_{entry.entry_id}"]
    assert issue.translation_key == f"login_{result}_link"
    assert issue.translation_placeholders["url"] == "http://helper.example/"
    assert not hass.config_entries.flow.async_progress()
    # The helper keeps being asked: it retries by itself.
    assert len(await helper_asks(hass)) == 1

    await hass.services.async_call(DOMAIN, "set_session", {"jsessionid": "good"}, blocking=True)
    await hass.async_block_till_done()
    assert not issues(hass)


async def test_a_missing_helper_is_a_repair_issue(recorder_mock, hass, portal, freezer):
    await setup_entry(hass, jsessionid="")
    freezer.tick(HELPER_TIMEOUT + HELPER_WATCH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert "helper_missing" in issues(hass)

    await helper_asks(hass)
    assert not issues(hass)


async def test_no_issue_while_nothing_is_wanted(recorder_mock, hass, portal, freezer):
    await setup_entry(hass)
    freezer.tick(HELPER_TIMEOUT + HELPER_WATCH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not issues(hass)
