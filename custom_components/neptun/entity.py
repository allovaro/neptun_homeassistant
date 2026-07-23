"""Shared base class for Neptun entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import NeptunCoordinator


class NeptunEntity(CoordinatorEntity[NeptunCoordinator]):
    """Base for anything backed by the shared Neptun poll."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = False

    def __init__(self, coordinator: NeptunCoordinator, key: str) -> None:
        """Initialise the entity.

        ``key`` doubles as the object id so entity ids stay exactly as they were
        before this integration grew a coordinator.
        """
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{DOMAIN}_{key}"
        self._attr_unique_id = f"{coordinator.client.host}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Group every entity under one controller device."""
        status = self.coordinator.data
        info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.client.host)},
            manufacturer="Neptun",
            name="Neptun",
            configuration_url=f"http://{self.coordinator.client.host}",
        )
        if status is not None:
            info["model"] = status.model
            if status.mac:
                info["connections"] = {(CONNECTION_NETWORK_MAC, status.mac)}
        return info
