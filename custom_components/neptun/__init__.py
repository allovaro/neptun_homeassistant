"""Support for Neptun water leak protection systems.

Configured from YAML, for example::

    neptun:
      host: 192.168.1.110
      scan_interval: 30

Everything else is discovered from the controller itself: how many wired leak
lines it has, which water meter slots are actually set up, and how many
wireless sensors are paired.  The options below only exist to override that.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_TIMEOUT
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_COUNTERS,
    CONF_LINES,
    CONF_RETRIES,
    CONF_WIRELESS_RECORD_SIZE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FALLBACK_COUNTERS,
    FALLBACK_LINES,
    PLATFORMS,
)
from .coordinator import NeptunCoordinator, NeptunRuntime
from .neptun_tcp import (
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    NeptunClient,
    NeptunStatus,
)

_LOGGER = logging.getLogger(__name__)

# Kept at module level because the platforms have always imported it from here.
ATTRIBUTION = "Data provided by Neptun water leak detector"
DATA_NEPTUN = DOMAIN

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.time_period,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_RETRIES, default=DEFAULT_RETRIES): cv.positive_int,
                vol.Optional(CONF_COUNTERS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=8)
                ),
                vol.Optional(CONF_LINES): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=16)
                ),
                vol.Optional(CONF_WIRELESS_RECORD_SIZE, default=4): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _resolve_counters(status: NeptunStatus | None, override: int | None) -> list[int]:
    """Work out which counter slots deserve an entity.

    The controller exposes a fixed number of slots and marks the unused ones
    with a zero step, so an unconfigured meter is told apart from one that
    genuinely reads zero.
    """
    if override is not None:
        return list(range(1, override + 1))
    if status is None:
        return list(range(1, FALLBACK_COUNTERS + 1))
    return [counter.index for counter in status.counters if counter.step]


def _resolve_lines(status: NeptunStatus | None, override: int | None) -> int:
    """Work out how many wired leak lines to expose."""
    if override is not None:
        return override
    if status is None:
        return FALLBACK_LINES
    return len(status.lines)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Neptun integration."""
    conf = config[DOMAIN]

    client = NeptunClient(
        host=conf[CONF_HOST],
        port=conf[CONF_PORT],
        timeout=conf[CONF_TIMEOUT],
        retries=conf[CONF_RETRIES],
        wireless_record_size=conf[CONF_WIRELESS_RECORD_SIZE],
    )
    coordinator = NeptunCoordinator(hass, client, conf[CONF_SCAN_INTERVAL])

    await coordinator.async_refresh()
    status = coordinator.data
    if status is None:
        _LOGGER.warning(
            "Neptun %s did not answer during start-up; setting up with default "
            "entities, which stay unavailable until it does",
            client.host,
        )
    else:
        _LOGGER.debug(
            "Neptun %s (%s) reported %d wired lines, %d counter slots, "
            "%d wireless sensors",
            status.model,
            status.mac,
            len(status.lines),
            len(status.counters),
            len(status.wireless),
        )

    runtime = NeptunRuntime(
        coordinator=coordinator,
        lines=_resolve_lines(status, conf.get(CONF_LINES)),
        counters=_resolve_counters(status, conf.get(CONF_COUNTERS)),
        wireless=len(status.wireless) if status else 0,
    )
    hass.data[DOMAIN] = runtime

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True
