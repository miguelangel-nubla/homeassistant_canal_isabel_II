"""Sensor platform for Canal de Isabel II.

The hourly history lives in an external statistic (see statistics.py), which
is what the Energy panel uses. The entities here only show the latest values.
"""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import PortalData
from .const import DEFAULT_NAME, DOMAIN
from .csv_parser import Reading
from .meter_parser import MeterSummary
from .statistics import consumption_statistic_id

_LOGGER = logging.getLogger(__name__)


def _readings_for(data: Optional[PortalData], contract_id: str) -> List[Reading]:
    if data is None:
        return []
    return [reading for reading in data.readings if reading.contract == contract_id]


def _meter_for(data: Optional[PortalData], contract_id: str) -> Optional[MeterSummary]:
    """Return the page's meter summary if it belongs to this contract.

    The page shows the summary of one contract only. It is matched by meter
    number, or taken as-is when the CSV holds a single contract.
    """
    if data is None or data.meter is None:
        return None
    contracts = {reading.contract for reading in data.readings}
    meters = {reading.meter for reading in _readings_for(data, contract_id)}
    if data.meter.meter and data.meter.meter in meters:
        return data.meter
    if contracts == {contract_id}:
        return data.meter
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    registry = er.async_get(hass)
    with_consumption: set = set()
    with_meter: set = set()

    @callback
    def add_new_entities() -> None:
        """Create the sensors of contracts (and meter readings) not seen before.

        Runs on every update, so sensors also appear when the first fetch
        had no data.
        """
        data: Optional[PortalData] = coordinator.data
        if data is None:
            return
        entities: List[SensorEntity] = []
        for contract_id in sorted({reading.contract for reading in data.readings}):
            if contract_id not in with_consumption:
                with_consumption.add(contract_id)
                # The old "Total" entity only existed to carry statistics,
                # which now live in the external statistic.
                old_total = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"canal_ii_total_{contract_id}"
                )
                if old_total:
                    registry.async_remove(old_total)
                entities.append(CanalIsabelIIConsumptionSensor(coordinator, contract_id))
            if contract_id not in with_meter and _meter_for(data, contract_id) is not None:
                with_meter.add(contract_id)
                entities.append(CanalIsabelIIMeterReadingSensor(coordinator, contract_id))
        if entities:
            async_add_entities(entities)

    add_new_entities()
    if not with_consumption:
        _LOGGER.warning("No readings received from Canal de Isabel II yet; the sensors appear when there are.")
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


class _ContractSensor(CoordinatorEntity, SensorEntity):
    """Base for the sensors of one contract."""

    # The device carries the contract, so entity names stay short.
    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, contract_id: str) -> None:
        super().__init__(coordinator)
        self._contract_id = contract_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, contract_id)},
            name=f"{DEFAULT_NAME} {contract_id}",
            manufacturer=DEFAULT_NAME,
        )


class CanalIsabelIIConsumptionSensor(_ContractSensor):
    """Liters used in the most recent hour published by the portal."""

    def __init__(self, coordinator: DataUpdateCoordinator, contract_id: str) -> None:
        super().__init__(coordinator, contract_id)
        self._attr_name = "Consumption"
        self._attr_unique_id = f"canal_ii_consumption_{contract_id}"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.VOLUME
        # No state class: the hourly history is written as an external
        # statistic, so Home Assistant must not build its own from this state.
        self._attr_icon = "mdi:water"

    def _latest(self) -> Optional[Reading]:
        readings = _readings_for(self.coordinator.data, self._contract_id)
        return max(readings, key=lambda reading: reading.start) if readings else None

    @property
    def native_value(self) -> Optional[float]:
        latest = self._latest()
        return latest.liters if latest else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        latest = self._latest()
        if latest is None:
            return {}
        return {
            "reading_date": latest.label,
            "reading_start": latest.start.isoformat(),
            "period": latest.period,
            "meter_id": latest.meter,
            "address": latest.address,
            "frequency": latest.frequency,
            "statistic_id": consumption_statistic_id(self._contract_id),
        }


class CanalIsabelIIMeterReadingSensor(_ContractSensor):
    """Absolute reading of the physical meter, the figure used on the bill."""

    def __init__(self, coordinator: DataUpdateCoordinator, contract_id: str) -> None:
        super().__init__(coordinator, contract_id)
        self._attr_name = "Meter reading"
        self._attr_unique_id = f"canal_ii_meter_{contract_id}"
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"
        self._summary: Optional[MeterSummary] = _meter_for(coordinator.data, contract_id)

    def _handle_coordinator_update(self) -> None:
        # Keep the last known reading when a fetch comes back without one.
        summary = _meter_for(self.coordinator.data, self._contract_id)
        if summary is not None:
            self._summary = summary
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> Optional[float]:
        return self._summary.reading_m3 if self._summary else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if self._summary is None:
            return {}
        return {
            "reading_at": self._summary.read_at.isoformat() if self._summary.read_at else None,
            "raw_reading": self._summary.raw,
            "meter_id": self._summary.meter,
            "address": self._summary.address,
        }
