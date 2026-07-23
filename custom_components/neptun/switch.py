"""Valve and dry-mode control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import (
    ENTITY_ID_FORMAT,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import NeptunCoordinator, NeptunRuntime
from .entity import NeptunEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Neptun switches."""
    if discovery_info is None:
        # Legacy "- platform: neptun" block; see the note in binary_sensor.py.
        return

    runtime: NeptunRuntime = hass.data[DOMAIN]
    async_add_entities(
        [
            NeptunValvesSwitch(runtime.coordinator),
            NeptunDrySwitch(runtime.coordinator),
        ]
    )


class NeptunValvesSwitch(NeptunEntity, SwitchEntity):
    """Opens and closes the water valves."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator: NeptunCoordinator) -> None:
        """Initialise the valve switch."""
        super().__init__(coordinator, "valves")
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_valves")

    @property
    def is_on(self) -> bool | None:
        """Return True while the valves are open."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.valves_open

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Open the valves."""
        await self.coordinator.async_set_state(valves_open=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Close the valves."""
        await self.coordinator.async_set_state(valves_open=False)


class NeptunDrySwitch(NeptunEntity, SwitchEntity):
    """Toggles dry mode, which suppresses the floor sensors while cleaning."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:spray-bottle"

    def __init__(self, coordinator: NeptunCoordinator) -> None:
        """Initialise the dry mode switch."""
        super().__init__(coordinator, "dry")
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_dry")

    @property
    def is_on(self) -> bool | None:
        """Return True while dry mode is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.dry_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable dry mode, leaving the valves where they are."""
        await self.coordinator.async_set_state(dry_mode=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable dry mode, leaving the valves where they are."""
        await self.coordinator.async_set_state(dry_mode=False)
