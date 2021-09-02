"""Support for monitoring the state of Neptun sensors"""
import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_OPENING,
    DEVICE_CLASS_SAFETY,
    PLATFORM_SCHEMA,
    BinarySensorEntity,
)

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_MONITORED_VARIABLES,
    STATE_ON,
)

import homeassistant.helpers.config_validation as cv

from . import (
    ATTRIBUTION,
    DATA_NEPTUN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Droplet"
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_MONITORED_VARIABLES):
        vol.All(cv.ensure_list, [cv.string])}
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Neptun sensors"""
    host = hass.data.get(DATA_NEPTUN)
    if not host:
        return False

    sensors = config[CONF_MONITORED_VARIABLES]

    dev = []
    for sensor in sensors:
        dev.append(NeptunBinarySensor(host, sensor))

    add_entities(dev, True)


class NeptunBinarySensor(BinarySensorEntity):
    """Representation of a Neptun Leak Detector sensor."""

    def __init__(self, _host, sensor):
        """Initialize a new Neptun Leak Detector sensor."""
        self.neptun_instance = _host
        self.sensor_name = sensor
        self._state = None
        self.data = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'neptun_{self.sensor_name}'

    @property
    def available(self) -> bool:
        """Return True if sensor is available."""
        return self.neptun_instance.available

    @property
    def icon(self):
        if self.sensor_name == 'dry':
            return 'mdi:spray-bottle'
        elif self.sensor_name == 'alarm':
            return 'mdi:water-pump'
        else:
            return 'mdi:water'

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.data == STATE_ON

    @property
    def device_class(self):
        """Return the class of this sensor."""
        if self.sensor_name == 'valves':
            return DEVICE_CLASS_OPENING
        elif self.sensor_name == 'dry':
            return DEVICE_CLASS_SAFETY
        elif self.sensor_name == 'alarm':
            return DEVICE_CLASS_SAFETY
        else:
            return DEVICE_CLASS_PROBLEM

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the Neptun."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def update(self):
        """Update state of sensor."""
        self.neptun_instance.update()

        if self.neptun_instance.available:
            sensors = self.neptun_instance.neptun.parse_data()
            for sensor in sensors:
                if sensor == self.sensor_name:
                    self.data = sensors[sensor]

