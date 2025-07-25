# custom_components/ice_ha/binary_sensor.py

import logging
from typing import Any
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType
from .const import DOMAIN
from . import ICEClientWrapper

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    _LOGGER.debug("Setting up binary_sensor platform for %s", config_entry.entry_id)
    client_wrapper: ICEClientWrapper = hass.data[DOMAIN][config_entry.entry_id]

    binary_sensors_to_add = [
        {
            "device_id_on_server": "ice_armed_state",
            "name": "ICE Armed",
            "device_class": BinarySensorDeviceClass.SAFETY,
            "ha_event_command": "pong_update",
            "attribute_key": "is_armed",
            "initial_state": False
        },
        {
            "device_id_on_server": "ice_normal_state",
            "name": "ICE Normal",
            "device_class": BinarySensorDeviceClass.SAFETY,
            "ha_event_command": "pong_update",
            "attribute_key": "is_normal",
            "initial_state": False
        },
        {
            "device_id_on_server": "server_connection_status",
            "name": "Server Connection",
            "device_class": BinarySensorDeviceClass.CONNECTIVITY,
            "ha_event_command": "pong_update",
            "attribute_key": "server_connected",
            "initial_state": False
        },
        {
            "device_id_on_server": "html_connection_status",
            "name": "HTML Connection",
            "device_class": BinarySensorDeviceClass.CONNECTIVITY,
            "ha_event_command": "pong_update",
            "attribute_key": "html_connected",
            "initial_state": False
        },
        {
            "type": "binary", # Explicitly mark type for clarity, though not used in this file for filtering
            "device_id_on_server": "pc_connection_status",
            "name": "PC Connection",
            "device_class": BinarySensorDeviceClass.CONNECTIVITY,
            "ha_event_command": "pong_update",
            "attribute_key": "pc_connected",
            "initial_state": False
        }
    ]

    entities = []
    for sensor_info in binary_sensors_to_add:
        entities.append(
            ICESocketIOBinarySensor(
                client_wrapper,
                sensor_info["device_id_on_server"],
                sensor_info["name"],
                sensor_info["device_class"],
                sensor_info["ha_event_command"],
                sensor_info["attribute_key"],
                sensor_info["initial_state"],
                config_entry.entry_id,
                config_entry.title
            )
        )
    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} binary sensors for ICE server: {client_wrapper.host}")


class ICESocketIOBinarySensor(BinarySensorEntity):
    """Representation of a Socket.IO Binary Sensor linked to ICE server events."""

    def __init__(
        self,
        client_wrapper: ICEClientWrapper,
        device_id_on_server: str,
        name: str,
        device_class: BinarySensorDeviceClass,
        ha_event_command: str,
        attribute_key: str,
        initial_state: bool,
        config_entry_id: str,
        config_entry_title: str
    ) -> None:
        """Initialize the binary sensor."""
        self._client_wrapper = client_wrapper
        self._device_id_on_server = device_id_on_server
        self._name = name
        self._device_class = device_class
        self._ha_event_command = ha_event_command
        self._attribute_key = attribute_key
        self._state = initial_state
        self._config_entry_id = config_entry_id
        self._config_entry_title = config_entry_title

        self._unique_id = f"{config_entry_id}_{device_id_on_server}"

        _LOGGER.debug(f"Initializing binary sensor: {self._name} (Unique ID: {self._unique_id}, Server ID: {self._device_id_on_server})")

    @property
    def unique_id(self) -> str:
        """Return a unique ID to be used by `home-assistant_v2.db`."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the device class of the binary sensor."""
        return self._device_class

    @property
    def should_poll(self) -> bool:
        """Return True if entity should be polled. False if entity pushes its state."""
        return False

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for this sensor."""
        return {
            "identifiers": {(DOMAIN, self._config_entry_id)},
            "name": self._config_entry_title,
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to Home Assistant."""
        _LOGGER.debug(f"Binary sensor {self._name} added to HASS. Registering listener for HA event: {DOMAIN}_server_command_{self._ha_event_command}")

        self.async_on_remove(
            self._client_wrapper.hass.bus.async_listen(
                f"{DOMAIN}_server_command_{self._ha_event_command}",
                self._handle_server_update
            )
        )
        self._client_wrapper.register_ha_sensor(self._unique_id, self)


    @callback
    def _handle_server_update(self, event: Event) -> None:
        """
        Handle incoming server update events from HA event bus.
        This will be a generic handler for 'pong_update' events.
        """
        event_data = event.data
        _LOGGER.debug(f"Binary Sensor {self._name}: Generic update received for event: {event.event_type} - Data: {event_data}")

        if self._attribute_key in event_data:
            new_val = event_data.get(self._attribute_key)
            if isinstance(new_val, bool):
                self.update_state(new_val)
            else:
                _LOGGER.warning(f"Binary sensor '{self._name}' received non-boolean value for '{self._attribute_key}': {new_val}")
        else:
            _LOGGER.debug(f"Binary sensor '{self._name}' did not find key '{self._attribute_key}' in event data.")


    @callback
    def update_state(self, new_state: bool) -> None:
        """
        Update the state of the binary sensor.
        This function will be called directly from ICEClientWrapper's pong handler.
        """
        if self._state != new_state:
            _LOGGER.info(f"Updating binary sensor '{self._name}' from {self._state} to {new_state}")
            self._state = new_state
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Binary sensor '{self._name}' state is already {self._state}, no update needed.")