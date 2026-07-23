"""Leak lines, valve position, dry mode and the alarm flag as binary sensors."""
from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import NeptunCoordinator, NeptunRuntime
from .entity import NeptunEntity
from .neptun_tcp import NeptunStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Neptun binary sensors."""
    if discovery_info is None:
        # A leftover "- platform: neptun" block from the pre-coordinator config.
        # Entities come from the neptun: section now, so ignore it rather than
        # setting everything up twice.
        return

    runtime: NeptunRuntime = hass.data[DOMAIN]
    coordinator = runtime.coordinator

    entities: list[BinarySensorEntity] = [
        NeptunBinarySensor(
            coordinator,
            f"sensor_{index}",
            BinarySensorDeviceClass.MOISTURE,
            lambda status, index=index: (
                status.lines[index - 1] if len(status.lines) >= index else None
            ),
        )
        for index in range(1, runtime.lines + 1)
    ]

    entities += [
        NeptunBinarySensor(
            coordinator,
            "valves",
            BinarySensorDeviceClass.OPENING,
            lambda status: status.valves_open,
            icon="mdi:water-pump",
        ),
        NeptunBinarySensor(
            coordinator,
            "dry",
            None,
            lambda status: status.dry_mode,
            icon="mdi:spray-bottle",
        ),
        NeptunBinarySensor(
            coordinator,
            "alarm",
            BinarySensorDeviceClass.SAFETY,
            lambda status: status.alarm,
            icon="mdi:water-alert",
        ),
    ]

    entities += [
        NeptunBinarySensor(
            coordinator,
            f"wireless_{index}",
            BinarySensorDeviceClass.MOISTURE,
            lambda status, index=index: (
                status.wireless[index - 1].alarm
                if len(status.wireless) >= index
                else None
            ),
        )
        for index in range(1, runtime.wireless + 1)
    ]

    async_add_entities(entities)


class NeptunBinarySensor(NeptunEntity, BinarySensorEntity):
    """One boolean read out of the shared controller poll."""

    def __init__(
        self,
        coordinator: NeptunCoordinator,
        key: str,
        device_class: BinarySensorDeviceClass | None,
        extract: Callable[[NeptunStatus], bool | None],
        icon: str | None = None,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, key)
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{key}")
        self._attr_device_class = device_class
        self._extract = extract
        if icon is not None:
            self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return the current value, or None if the controller stopped reporting it."""
        if self.coordinator.data is None:
            return None
        return self._extract(self.coordinator.data)
