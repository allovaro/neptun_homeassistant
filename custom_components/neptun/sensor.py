"""Water meter readings, plus diagnostics for paired wireless sensors."""
from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import NeptunCoordinator, NeptunRuntime
from .entity import NeptunEntity
from .neptun_tcp import Counter, NeptunStatus

_LOGGER = logging.getLogger(__name__)


def _counter(status: NeptunStatus, index: int) -> Counter | None:
    """Return the counter slot with the given one-based index."""
    for counter in status.counters:
        if counter.index == index:
            return counter
    return None


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Neptun sensors."""
    if discovery_info is None:
        # Legacy "- platform: neptun" block; see the note in binary_sensor.py.
        return

    runtime: NeptunRuntime = hass.data[DOMAIN]
    coordinator = runtime.coordinator

    entities: list[SensorEntity] = [
        NeptunCounterSensor(coordinator, index) for index in runtime.counters
    ]

    for index in range(1, runtime.wireless + 1):
        entities.append(
            NeptunWirelessDiagnostic(
                coordinator,
                f"wireless_{index}_battery",
                lambda status, index=index: (
                    status.wireless[index - 1].battery
                    if len(status.wireless) >= index
                    else None
                ),
                device_class=SensorDeviceClass.BATTERY,
                unit=PERCENTAGE,
            )
        )
        entities.append(
            NeptunWirelessDiagnostic(
                coordinator,
                f"wireless_{index}_signal",
                lambda status, index=index: (
                    status.wireless[index - 1].signal
                    if len(status.wireless) >= index
                    else None
                ),
                icon="mdi:signal",
            )
        )

    async_add_entities(entities)


class NeptunCounterSensor(NeptunEntity, SensorEntity):
    """A water meter reading, in cubic metres."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: NeptunCoordinator, index: int) -> None:
        """Initialise the counter."""
        super().__init__(coordinator, f"counter_{index}")
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_counter_{index}")
        self._index = index

    @property
    def native_value(self) -> float | None:
        """Return the meter reading."""
        if self.coordinator.data is None:
            return None
        counter = _counter(self.coordinator.data, self._index)
        return counter.cubic_metres if counter else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw reading and the meter's pulse weight."""
        if self.coordinator.data is None:
            return {}
        counter = _counter(self.coordinator.data, self._index)
        if counter is None:
            return {}
        return {"litres": counter.litres, "step": counter.step}


class NeptunWirelessDiagnostic(NeptunEntity, SensorEntity):
    """Battery or signal readout for a paired wireless sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: NeptunCoordinator,
        key: str,
        extract: Callable[[NeptunStatus], int | None],
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialise the diagnostic sensor."""
        super().__init__(coordinator, key)
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{key}")
        self._extract = extract
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if icon is not None:
            self._attr_icon = icon

    @property
    def native_value(self) -> int | None:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        return self._extract(self.coordinator.data)
