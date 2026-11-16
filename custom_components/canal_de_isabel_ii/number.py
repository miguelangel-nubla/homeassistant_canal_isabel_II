"""Number platform for Canal de Isabel II: the settings of the leak check.

Households differ: one has a drip irrigation that never stops, another a
meter that reports more of a trickle at rest. Each contract has its own two
settings, which Home Assistant keeps across restarts.
"""
from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .insights import LEAK_HOURS, REST_LITERS
from .sensor import ContractEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    known: set = set()

    @callback
    def add_new_entities() -> None:
        """Create the settings of each contract not seen before."""
        if coordinator.data is None:
            return
        new = {reading.contract for reading in coordinator.data.readings} - known
        known.update(new)
        async_add_entities(
            setting(coordinator, contract, runtime.leak_settings)
            for contract in sorted(new)
            for setting in (RestThresholdNumber, LeakHoursNumber)
        )

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


class _LeakSetting(ContractEntity, RestoreNumber):
    """One setting of the leak check of a contract."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _setting: str
    _default: float

    def __init__(self, coordinator: DataUpdateCoordinator, contract_id: str, settings: dict) -> None:
        super().__init__(coordinator, contract_id)
        self._settings = settings
        self._attr_translation_key = self._setting
        self._attr_unique_id = f"canal_ii_{self._setting}_{contract_id}"
        self._attr_native_value = self._default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._apply(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._apply(value)
        self.async_write_ha_state()

    def _apply(self, value: float) -> None:
        self._attr_native_value = value
        self._settings.setdefault(self._contract_id, {})[self._setting] = value
        # The leak sensor judges the same readings again.
        self.coordinator.async_update_listeners()

    @property
    def available(self) -> bool:
        # A setting, not a reading: it does not depend on the last fetch.
        return True


class RestThresholdNumber(_LeakSetting):
    """Below how many liters an hour counts as at rest."""

    _setting = "rest_liters"
    _default = REST_LITERS
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.1
    _attr_icon = "mdi:water-off-outline"


class LeakHoursNumber(_LeakSetting):
    """How many published hours without rest make a possible leak."""

    _setting = "leak_hours"
    _default = LEAK_HOURS
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 6
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_icon = "mdi:timer-outline"
