import asyncio
import logging
import websockets
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, WEBSOCKET_PORT, HEARTBEAT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# List of platforms that this integration supports.
PLATFORMS = ["binary_sensor"]

# Dictionary to store connected clients and their last heartbeat time
CONNECTED_CLIENTS = {}
# Dictionary to store references to binary_sensor entities
PC_SENSORS = {}

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ICE WebSocket Server component."""
    hass.data.setdefault(DOMAIN, {})

    # Start the WebSocket server
    asyncio.create_task(_start_websocket_server(hass))
    _LOGGER.info(f"WebSocket server starting on port {WEBSOCKET_PORT}")

    # Start the heartbeat monitoring task
    asyncio.create_task(_monitor_heartbeats(hass))
    _LOGGER.info(f"Heartbeat monitor started with timeout {HEARTBEAT_TIMEOUT}s")

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ICE WebSocket Server from a config entry."""
    # Forward the setup to the binary_sensor platform
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "binary_sensor")
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the binary_sensor platform
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "binary_sensor")
    if unload_ok:
        # TODO: Gracefully stop the websocket server if it's running
        _LOGGER.info("ICE WebSocket Server integration unloaded.")
    return unload_ok

async def _websocket_handler(websocket, path):
    """Handle incoming WebSocket connections."""
    client_ip = websocket.remote_address[0]
    _LOGGER.info(f"New WebSocket connection from {client_ip}")

    # Assume client sends its name/ID on first connect or periodically
    # For simplicity, let's just use IP as ID for now.
    pc_id = client_ip

    # If this is a new PC, create a binary_sensor for it
    if pc_id not in PC_SENSORS:
        # This part requires the binary_sensor to be set up.
        # In a real integration, you might add a discovery mechanism or
        # require manual configuration of PCs.
        # For this example, we'll assume binary_sensor.py can handle dynamic creation
        # or that these IPs are pre-configured.
        _LOGGER.warning(f"PC {pc_id} connected but no sensor found. Ensure it's configured in binary_sensor.py or discovered.")
        # For this basic example, we'll just add it to connected clients
        # A more robust solution would dynamically create sensor entities here.

    CONNECTED_CLIENTS[pc_id] = datetime.now()
    _LOGGER.debug(f"Client {pc_id} added to connected list.")

    # Update sensor state to ON
    if pc_id in PC_SENSORS:
        sensor = PC_SENSORS[pc_id]
        if sensor.state != "on":
            sensor.set_state("on")
            _LOGGER.info(f"PC {pc_id} status updated to ON.")
    else:
        _LOGGER.warning(f"Sensor for {pc_id} not found. Cannot update state.")


    try:
        async for message in websocket:
            # Assume any message is a heartbeat
            _LOGGER.debug(f"Received heartbeat from {pc_id}: {message}")
            CONNECTED_CLIENTS[pc_id] = datetime.now()
            # If state was OFF, turn it ON again (e.g., after temporary disconnect)
            if pc_id in PC_SENSORS:
                sensor = PC_SENSORS[pc_id]
                if sensor.state != "on":
                    sensor.set_state("on")
                    _LOGGER.info(f"PC {pc_id} status updated to ON (heartbeat).")

    except websockets.exceptions.ConnectionClosedOK:
        _LOGGER.info(f"WebSocket connection from {pc_id} closed normally.")
    except websockets.exceptions.ConnectionClosedError as e:
        _LOGGER.warning(f"WebSocket connection from {pc_id} closed with error: {e}")
    except Exception as e:
        _LOGGER.error(f"Error in WebSocket handler for {pc_id}: {e}")
    finally:
        # Client disconnected or error occurred
        if pc_id in CONNECTED_CLIENTS:
            del CONNECTED_CLIENTS[pc_id]
            _LOGGER.info(f"Client {pc_id} removed from connected list.")
        # Mark sensor offline immediately on disconnect
        if pc_id in PC_SENSORS:
            sensor = PC_SENSORS[pc_id]
            if sensor.state != "off":
                sensor.set_state("off")
                _LOGGER.info(f"PC {pc_id} status updated to OFF (disconnected).")


async def _start_websocket_server(hass: HomeAssistant):
    """Start the WebSocket server."""
    try:
        server = await websockets.serve(
            _websocket_handler, "0.0.0.0", WEBSOCKET_PORT
        )
        await server.wait_closed()
    except Exception as e:
        _LOGGER.error(f"Failed to start WebSocket server: {e}")

async def _monitor_heartbeats(hass: HomeAssistant):
    """Monitor heartbeats and mark PCs offline if timeout occurs."""
    while True:
        await asyncio.sleep(5) # Check every 5 seconds
        now = datetime.now()
        offline_threshold = timedelta(seconds=HEARTBEAT_TIMEOUT)

        # Create a copy of keys to avoid RuntimeError: dictionary changed size during iteration
        for pc_id in list(CONNECTED_CLIENTS.keys()):
            last_heartbeat = CONNECTED_CLIENTS.get(pc_id)
            if last_heartbeat and (now - last_heartbeat) > offline_threshold:
                _LOGGER.warning(f"PC {pc_id} heartbeat timeout. Marking offline.")
                # Remove from connected clients
                del CONNECTED_CLIENTS[pc_id]
                # Update sensor state to OFF
                if pc_id in PC_SENSORS:
                    sensor = PC_SENSORS[pc_id]
                    if sensor.state != "off":
                        sensor.set_state("off")
                        _LOGGER.info(f"PC {pc_id} status updated to OFF (heartbeat timeout).")
                else:
                    _LOGGER.warning(f"Sensor for {pc_id} not found. Cannot update state.")