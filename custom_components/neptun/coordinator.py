"""Single polling loop shared by every Neptun entity.

The controller only serves one session at a time, so all entities read from one
coordinator instead of each opening its own connection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .neptun_tcp import NeptunClient, NeptunError, NeptunStatus

_LOGGER = logging.getLogger(__name__)


class NeptunCoordinator(DataUpdateCoordinator[NeptunStatus]):
    """Polls one controller and hands the result to every entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeptunClient,
        scan_interval: timedelta,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {client.host}",
            update_interval=scan_interval,
        )
        self.client = client

    async def _async_update_data(self) -> NeptunStatus:
        """Fetch the current controller status."""
        try:
            return await self.hass.async_add_executor_job(self.client.get_status)
        except NeptunError as err:
            raise UpdateFailed(f"Neptun {self.client.host}: {err}") from err

    async def async_set_state(
        self, *, valves_open: bool | None = None, dry_mode: bool | None = None
    ) -> None:
        """Change valve position and/or dry mode.

        The controller takes both flags in a single frame, so whichever one the
        caller left out is filled in from the last poll.  Without this, toggling
        dry mode would also fling the valves open.
        """
        if self.data is None:
            raise HomeAssistantError(
                f"Neptun {self.client.host} has not been read yet, refusing to "
                "write a half-known state"
            )
        target_valves = self.data.valves_open if valves_open is None else valves_open
        target_dry = self.data.dry_mode if dry_mode is None else dry_mode

        try:
            await self.hass.async_add_executor_job(
                self.client.set_state, target_valves, target_dry
            )
        except NeptunError as err:
            raise HomeAssistantError(f"Neptun {self.client.host}: {err}") from err

        await self.async_request_refresh()


@dataclass
class NeptunRuntime:
    """What the platforms need in order to build their entity lists."""

    coordinator: NeptunCoordinator
    lines: int
    counters: list[int]
    wireless: int
