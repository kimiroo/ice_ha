import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CONF_PC_IP, CONF_PC_NAME
# Get PC_SENSORS dict from __init__.py and share across the integrations
# This dict is used in _websocket_handler, _monitor_heartbeats
PC_SENSORS = {}

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
):
    """Set up the binary sensor platform."""
    # Get PC information from the config entry
    pc_ip = config_entry.data[CONF_PC_IP]
    pc_name = config_entry.data.get(CONF_PC_NAME) or pc_ip # Use IP if name isn't set

    # Create the sensor entity
    sensor = PCStatusBinarySensor(hass, pc_ip, pc_name)
    async_add_entities([sensor], True)

    # Store reference in the global dict for __init__.py to update
    PC_SENSORS[pc_ip] = sensor
    _LOGGER.debug(f"Sensor for PC {pc_name} ({pc_ip}) added and stored.")


class PCStatusBinarySensor(BinarySensorEntity):
    """Representation of a PC status binary sensor."""

    def __init__(self, hass: HomeAssistant, pc_id: str, name: str):
        """Initialize the PC status sensor."""
        self._hass = hass
        self._pc_id = pc_id # This is the IP address from the client
        self._attr_name = name
        self._attr_unique_id = f"pc_status_{pc_id.replace('.', '_')}"
        self._attr_is_on = False # Initial state is off

        # Optional: Device info for better organization in HA
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pc_id)}, # Unique identifier for the device
            name=name,
            model="PC Monitor",
            manufacturer="Custom Integration",
        )

    @property
    def is_on(self):
        """Return true if the PC is online."""
        return self._attr_is_on

    def set_state(self, state: str):
        """Update the sensor's state."""
        new_state = state.lower() == "on"
        if self._attr_is_on != new_state:
            self._attr_is_on = new_state
            self.schedule_update_ha_state() # Request HA to update the state
            _LOGGER.debug(f"Sensor {self.entity_id} state changed to {state}")

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return "presence" # Or 'connectivity', 'running' etc.