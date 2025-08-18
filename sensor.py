# custom_components/ice_ha/sensor.py

import logging
from typing import Any
from homeassistant.components.sensor import SensorEntity # Import SensorEntity
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
    """Set up the regular sensor platform."""
    _LOGGER.debug("Setting up sensor platform for %s", config_entry.entry_id)
    client_wrapper: ICEClientWrapper = hass.data[DOMAIN][config_entry.entry_id]

    regular_sensors_to_add = [
        {
            "device_id_on_server": "html_clients_count",
            "name": "HTML Clients Count",
            "unit_of_measurement": "clients",
            "icon": "mdi:account-group",
            "ha_event_command": "pong_update",
            "attribute_key": "html_count",
            "initial_state": 0
        },
        {
            "device_id_on_server": "ha_clients_count",
            "name": "HA Clients Count",
            "unit_of_measurement": "clients",
            "icon": "mdi:account-group",
            "ha_event_command": "pong_update",
            "attribute_key": "ha_count",
            "initial_state": 0
        },
        {
            "device_id_on_server": "pc_clients_count",
            "name": "PC Clients Count",
            "unit_of_measurement": "clients",
            "icon": "mdi:desktop-classic",
            "ha_event_command": "pong_update",
            "attribute_key": "pc_count",
            "initial_state": 0
        }
    ]

    entities = []
    for sensor_info in regular_sensors_to_add:
        entities.append(
            ICESocketIOSensor(
                client_wrapper,
                sensor_info["device_id_on_server"],
                sensor_info["name"],
                sensor_info.get("unit_of_measurement"),
                sensor_info.get("icon"),
                sensor_info["ha_event_command"],
                sensor_info["attribute_key"],
                sensor_info["initial_state"],
                config_entry.entry_id,
                config_entry.title
            )
        )
    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} regular sensors for ICE server: {client_wrapper.host}")


class ICESocketIOSensor(SensorEntity):
    """Representation of a Socket.IO Sensor (for integer values) linked to ICE server events."""

    def __init__(
        self,
        client_wrapper: ICEClientWrapper,
        device_id_on_server: str,
        name: str,
        unit_of_measurement: str | None,
        icon: str | None,
        ha_event_command: str,
        attribute_key: str,
        initial_state: int,
        config_entry_id: str,
        config_entry_title: str
    ) -> None:
        """Initialize the sensor."""
        self._client_wrapper = client_wrapper
        self._device_id_on_server = device_id_on_server
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._icon = icon
        self._ha_event_command = ha_event_command
        self._attribute_key = attribute_key
        self._state = initial_state
        self._config_entry_id = config_entry_id
        self._config_entry_title = config_entry_title

        self._unique_id = f"{config_entry_id}_{device_id_on_server}"

        _LOGGER.debug(f"Initializing sensor: {self._name} (Unique ID: {self._unique_id}, Server ID: {self._device_id_on_server})")

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def native_value(self) -> int | None:
        """Return the current value of the sensor."""
        return self._state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        return self._icon

    @property
    def device_class(self) -> None:
        """Return the device class of the sensor."""
        return None

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
        _LOGGER.debug(f"Sensor {self._name} added to HASS. Registering listener for HA event: {DOMAIN}_server_command_{self._ha_event_command}")

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
        _LOGGER.debug(f"Regular Sensor {self._name}: Generic update received for event: {event.event_type} - Data: {event_data}")

        if self._attribute_key in event_data:
            new_val = event_data.get(self._attribute_key)
            if isinstance(new_val, int):
                self.update_state(new_val)
            else:
                _LOGGER.warning(f"Regular sensor '{self._name}' received non-integer value for '{self._attribute_key}': {new_val}")
        else:
            _LOGGER.debug(f"Regular sensor '{self._name}' did not find key '{self._attribute_key}' in event data.")


    @callback
    def update_state(self, new_state: int) -> None:
        """
        Update the state of the regular sensor.
        This function will be called directly from ICEClientWrapper's pong handler.
        """
        if self._state != new_state:
            _LOGGER.info(f"Updating sensor '{self._name}' from {self._state} to {new_state}")
            self._state = new_state
            self.async_write_ha_state()
        else:
            _LOGGER.debug(f"Sensor '{self._name}' state is already {self._state}, no update needed.")