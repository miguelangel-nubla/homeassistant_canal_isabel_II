"""Binary sensor platform for Canal de Isabel II: the possible leak."""
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .insights import LEAK_HOURS, REST_LITERS
from .sensor import ContractEntity, insights_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
    known: set = set()

    @callback
    def add_new_entities() -> None:
        """Create the sensor of each contract not seen before."""
        if coordinator.data is None:
            return
        new = {reading.contract for reading in coordinator.data.readings} - known
        known.update(new)
        async_add_entities(CanalIsabelIILeakSensor(coordinator, contract) for contract in sorted(new))

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


class CanalIsabelIILeakSensor(ContractEntity, BinarySensorEntity):
    """On when the meter has not rested for two days of published hours.

    A household uses no water for some hour of every day or two. A meter
    that never rests points at a dripping cistern or tap, or a leak after
    the meter. The portal publishes with a day of delay, so this
    catches the leaks that last, not a burst pipe.
    """

    def __init__(self, coordinator: DataUpdateCoordinator, contract_id: str) -> None:
        super().__init__(coordinator, contract_id)
        self._attr_translation_key = "possible_leak"
        self._attr_unique_id = f"canal_ii_possible_leak_{contract_id}"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:pipe-leak"

    @property
    def is_on(self) -> Optional[bool]:
        return insights_for(self.coordinator.data, self._contract_id).possible_leak

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        found = insights_for(self.coordinator.data, self._contract_id)
        return {
            "hours_without_pause": found.hours_without_pause,
            "hours_for_a_leak": LEAK_HOURS,
            "liters_per_hour_at_rest": REST_LITERS,
            "last_hour_at_rest": found.last_pause.isoformat() if found.last_pause else None,
            "data_until": found.data_until.isoformat() if found.data_until else None,
        }
