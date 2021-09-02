"""Platform for sensor integration."""
import logging

import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
)

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_MONITORED_VARIABLES,
)

import homeassistant.helpers.config_validation as cv

from . import (
    ATTRIBUTION,
    DATA_NEPTUN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Counter"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_MONITORED_VARIABLES):
        vol.All(cv.ensure_list, [cv.string])}
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""
    host = hass.data.get(DATA_NEPTUN)
    if not host:
        return False

    sensors = config[CONF_MONITORED_VARIABLES]

    dev = []
    for sensor in sensors:
        dev.append(NeptunCounterSensor(host, sensor))

    add_entities(dev, True)


class NeptunCounterSensor(SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, _host, _sensor):
        """Initialize the sensor."""
        self._state = None
        self._name = _sensor
        self._host = _host

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'neptun_{self._name}'

    @property
    def icon(self):
        return 'mdi:counter'

    @property
    def available(self) -> bool:
        """Return True if sensor is available."""
        return self._host.available

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'м³'

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the Neptun."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def update(self):
        """Update state of sensor."""
        self._host.update()

        if self._host.available:
            sensors = self._host.neptun.parse_data()
            for sensor in sensors:
                if sensor == self._name:
                    self._state = sensors[sensor]

