"""Support for interacting with Digital Ocean droplets."""
import logging

import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_NAME,
    STATE_ON,
    STATE_OFF,
)
import homeassistant.helpers.config_validation as cv

from . import (
    ATTRIBUTION,
    DATA_NEPTUN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Valves"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Neptun valves switch."""
    host = hass.data.get(DATA_NEPTUN)
    name = config[CONF_NAME]
    if not host:
        return False

    add_entities([NeptunValvesSwitch(host, name)], True)


class NeptunValvesSwitch(SwitchEntity):
    """Representation of a Neptun switch."""

    def __init__(self, _host, _name):
        """Initialize a new Neptun switch."""
        self.neptun_instance = _host
        self.switch_name = _name
        self.data = None
        self._state = None

    @property
    def name(self):
        """Return the name of the switch."""
        return f'neptun_{self.switch_name}'

    @property
    def available(self) -> bool:
        """Return True if sensor is available."""
        return self.neptun_instance.available

    @property
    def icon(self):
        if self.switch_name == 'valves':
            return 'mdi:water-pump'
        else:
            return 'mdi:spray-bottle'

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state == STATE_ON

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the Neptun."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def turn_on(self, **kwargs):
        """Turn on the switch."""
        if self.switch_name == 'valves':
            self.neptun_instance.neptun.set_state(True, False)
            self._state = STATE_ON
        if self.switch_name == 'dry':
            self.neptun_instance.neptun.set_state(False, True)
            self._state = STATE_ON

    def turn_off(self, **kwargs):
        """Turn off the switch."""
        if self.switch_name == 'valves':
            self.neptun_instance.neptun.set_state(False, False)
            self._state = STATE_OFF
        if self.switch_name == 'dry':
            self.neptun_instance.neptun.set_state(False, False)
            self._state = STATE_OFF

    def update(self):
        """Get the latest data from the device and update the data."""
        self.neptun_instance.update()
        valves = False
        dry = False
        if self.neptun_instance.available:
            valves = self.neptun_instance.neptun.get_valve_state()
            dry = self.neptun_instance.neptun.get_dry_flag_state()

        if self.switch_name == 'valves':
            self._state = valves
        if self.switch_name == 'dry':
            self._state = dry

