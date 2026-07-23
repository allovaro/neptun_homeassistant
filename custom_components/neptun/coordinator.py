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

from .const import DEFAULT_FAILURE_TOLERANCE, DOMAIN
from .neptun_tcp import NeptunClient, NeptunError, NeptunStatus

_LOGGER = logging.getLogger(__name__)


class NeptunCoordinator(DataUpdateCoordinator[NeptunStatus]):
    """Polls one controller and hands the result to every entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeptunClient,
        scan_interval: timedelta,
        failure_tolerance: int = DEFAULT_FAILURE_TOLERANCE,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {client.host}",
            update_interval=scan_interval,
        )
        self.client = client
        self.failure_tolerance = max(0, failure_tolerance)
        self._consecutive_failures = 0

    async def _async_update_data(self) -> NeptunStatus:
        """Fetch the current controller status.

        Measured against the real controller, single polls fail roughly one time
        in seven, almost always as a sub-6-second blip that the client's spread
        retries already absorb — but occasionally as a ~50-second window that no
        amount of in-poll retrying can cross within one scan interval. Rather
        than flap every entity to unavailable for such a hiccup, hold the last
        good reading across a few failed polls and only surface unavailability
        once the controller has been unreachable long enough to look genuinely
        gone.

        The valve, dry-mode and leak state stay put while riding this out. That
        is safe because leak response lives in the controller itself, which
        closes the valves on its own with no help from Home Assistant; the worst
        case here is a stale reading on screen for a minute or two, not a missed
        physical response.
        """
        try:
            status = await self.hass.async_add_executor_job(self.client.get_status)
        except NeptunError as err:
            self._consecutive_failures += 1
            if (
                self.data is not None
                and self._consecutive_failures <= self.failure_tolerance
            ):
                _LOGGER.warning(
                    "Neptun %s unreachable (%d/%d before going unavailable): %s",
                    self.client.host,
                    self._consecutive_failures,
                    self.failure_tolerance,
                    err,
                )
                return self.data
            raise UpdateFailed(f"Neptun {self.client.host}: {err}") from err

        self._consecutive_failures = 0
        return status

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
