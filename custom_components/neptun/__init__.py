"""Support for Neptun water leak protection system"""
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.const import CONF_HOST
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

REQUIREMENTS = ['neptun_tcp==0.1.0']


_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by Neptun water leak detector"

CONF_DROPLETS = "types"

DATA_NEPTUN = "data_neptun"
DIGITAL_OCEAN_PLATFORMS = ["switch", "binary_sensor", "sensor"]
DOMAIN = "neptun"

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_HOST): cv.string})},
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up the neptun component."""

    conf = config[DOMAIN]
    host = conf[CONF_HOST]

    import sys
    path = hass.config.path('custom_components/neptun')
    if path not in sys.path:
        sys.path.insert(0, path)

    neptun_server = Neptun(host)

    hass.data[DATA_NEPTUN] = neptun_server

    return True


class Neptun:
    """Handle all communication with Neptun Leak Detector"""

    def __init__(self, host):
        """Initialize the Neptun connection."""
        from neptun_tcp import NeptunTcp

        self._host = host
        self.available = False
        self.neptun = NeptunTcp(self._host)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Use the data from neptun."""
        self.available = self.neptun.get_state()
        if not self.available:
            _LOGGER.error("No Neptun System found for the given address")

