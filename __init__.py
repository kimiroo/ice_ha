import datetime
import asyncio
import socketio
import logging
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ICEClientWrapper:
    def __init__(self, hass: HomeAssistant, client_name, host, port, use_ssl, auth_token):
        self.hass = hass
        self.client_name = client_name
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.auth_token = auth_token
        self.sio = socketio.AsyncClient()
        self._is_connected = False

        self._connect_task = None # To hold the background connection task
        self._reconnect_loop_task = None # To hold the continuous reconnection task
        self._event_result_check_loop_task = None # To hold the continuous event result check task
        self._ping_loop_task = None

        self._ha_event_object = {} # To hold HA event object for checking event result

        # Register Socket.IO event handlers
        self.sio.on('connect', self._on_connect)
        self.sio.on('disconnect', self._on_disconnect)
        self.sio.on('event', self._on_ice_event)
        self.sio.on('event_result', self._on_event_result)

    async def _on_connect(self):
        self._is_connected = True
        _LOGGER.info(f"Connected to Socket.IO server: {self.host}:{self.port}")

    async def _on_disconnect(self):
        self._is_connected = False
        _LOGGER.warning(f"Disconnected from Socket.IO server: {self.host}:{self.port}")

    async def _on_ice_event(self, data):
        """Handle server commands and fire HA events."""
        _LOGGER.info(f"Received 'server_command' from Socket.IO server: {data}")
        command = data.get("command")
        event_data = data.get("event_data", {})

        if command:
            await self.hass.bus.async_fire(
                f"{DOMAIN}_server_command_{command}",
                event_data
            )
            _LOGGER.debug(f"Fired HA event '{DOMAIN}_server_command_{command}' with data: {event_data}")
        else:
            _LOGGER.warning("Received 'server_command' without a 'command' field.")

    async def _on_event_result(self, data):
        received_id = data.get('id', None)
        server_result = data.get('result', 'failed')
        server_message = data.get('message', 'none')
        saved_event_object = self._ha_event_object.get(received_id, None)

        time_now = datetime.datetime.now()
        event_timestamp = saved_event_object.get('timestamp')
        time_diff = time_now - event_timestamp
        time_diff = time_diff.total_seconds()

        # Pop event object
        if saved_event_object:
            self._ha_event_object.pop(received_id)
        else:
            _LOGGER.warning(f"Received Event ID \'{received_id}\' is INVALID. (Not sent by this client or already validated event)")

        # Parse result
        if server_result == 'success' and time_diff <= 1:
            _LOGGER.info(f"Server reported handling Event ID \'{received_id}\' was successful. (message: {server_message})")

        elif server_result == 'success' and time_diff > 1:
            _LOGGER.warning(f"Event ID \'{received_id}\' took longer than expected. ({time_diff} seconds) (message: {server_message})")

        elif server_result != 'success' and time_diff <= 1:
            _LOGGER.error(f"Server reported handling Event ID \'{received_id}\' failed. (reason: {server_message})")

        else:
            _LOGGER.error(f"Server reported handling Event ID \'{received_id}\' failed and took longer than expected ({time_diff} seconds) (reason: {server_message})")

    async def _run_event_result_check_loop(self):
        """
        Continuously monitors event result.
        This runs as a background task.
        """
        while True:
            try:
                time_now = datetime.datetime.now()
                for event_id, event_obj in list(self._ha_event_object.items()):
                    time_diff = time_now - event_obj['timestamp']
                    time_diff = time_diff.total_seconds()

                    if time_diff > (5 * 60): # 5 minutes
                        _LOGGER.error(f"Event ID \'{event_id}\' is overdue. Removing event from saved event cache... (5 minutes)")
                        self._ha_event_object.pop(event_id)

                    elif time_diff > 1 and event_obj['is_valid']:
                        _LOGGER.warning(f"Event ID \'{event_id}\' is taking longer than expected to be processed by server.")
                        self._ha_event_object[event_id]['is_valid'] = False

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                _LOGGER.info("Event result check loop task was cancelled.")
                break # Exit the loop cleanly

            except Exception as e:
                _LOGGER.error(f"Error in result check loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    def start_event_result_check_loop(self):
        """Starts the continuous event result check background task."""
        if self._event_result_check_loop_task is None or self._event_result_check_loop_task.done():
            _LOGGER.debug("Starting event result check loop task.")
            self._event_result_check_loop_task = asyncio.create_task(self._run_event_result_check_loop())
        else:
            _LOGGER.debug("Event result check loop task is already running.")

    async def stop_event_result_check_loop(self):
        """Stops the continuous event result check background task."""
        if self._event_result_check_loop_task and not self._event_result_check_loop_task.done():
            _LOGGER.debug("Stopping event result check loop task.")
            self._event_result_check_loop_task.cancel()
            try:
                await self._event_result_check_loop_task # Await for the task to finish cancelling
            except asyncio.CancelledError:
                pass # Expected when cancelling the task
            except Exception as e:
                _LOGGER.error(f"Error while stopping event result check loop task: {e}")
            self._event_result_check_loop_task = None # Clear the task reference

    async def _run_reconnect_loop(self):
        """
        Continuously attempts to connect to the Socket.IO server if not connected.
        This runs as a background task.
        """
        reconnect_delay = 1

        while True:
            try:
                if not self.sio.connected:
                    _LOGGER.warning(f"Reconnect loop: Not connected, attempting to connect...")
                    connected = await self.connect()
                    if connected:
                        _LOGGER.info("Reconnect loop: Successfully reconnected to Socket.IO server.")
                    else:
                        _LOGGER.warning(f"Reconnect loop: Connection failed. Retrying in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)

            except asyncio.CancelledError:
                _LOGGER.info("Reconnect loop task was cancelled.")
                break # Exit the loop cleanly

            except Exception as e:
                _LOGGER.error(f"Error in reconnect loop: {e}", exc_info=True)
                await asyncio.sleep(reconnect_delay)

    def start_reconnect_loop(self):
        """Starts the continuous reconnection background task."""
        if self._reconnect_loop_task is None or self._reconnect_loop_task.done():
            _LOGGER.debug("Starting Socket.IO reconnection loop task.")
            self._reconnect_loop_task = asyncio.create_task(self._run_reconnect_loop())
        else:
            _LOGGER.debug("Reconnect loop task is already running.")

    async def stop_reconnect_loop(self):
        """Stops the continuous reconnection background task."""
        if self._reconnect_loop_task and not self._reconnect_loop_task.done():
            _LOGGER.debug("Stopping Socket.IO reconnection loop task.")
            self._reconnect_loop_task.cancel()
            try:
                await self._reconnect_loop_task # Await for the task to finish cancelling
            except asyncio.CancelledError:
                pass # Expected when cancelling the task
            except Exception as e:
                _LOGGER.error(f"Error while stopping reconnect loop task: {e}")
            self._reconnect_loop_task = None # Clear the task reference

    async def _run_ping_loop(self):
        """
        Continuously pings the ICE server.
        This runs as a background task.
        """
        while True:
            try:
                if self.sio.connected:
                    await self.sio.emit('ping')

                else:
                    _LOGGER.debug(f"Ping: Not connected.")

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                _LOGGER.info("Event result check loop task was cancelled.")
                break # Exit the loop cleanly

            except Exception as e:
                _LOGGER.error(f"Error in result check loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    def start_ping_loop(self):
        """Starts the continuous ping task."""
        if self._ping_loop_task is None or self._ping_loop_task.done():
            _LOGGER.debug("Starting ping loop task.")
            self._ping_loop_task = asyncio.create_task(self._run_ping_loop())
        else:
            _LOGGER.debug("Ping loop task is already running.")

    async def stop_ping_loop(self):
        """Stops the continuous ping task."""
        if self._ping_loop_task and not self._ping_loop_task.done():
            _LOGGER.debug("Stopping ping loop task.")
            self._ping_loop_task.cancel()
            try:
                await self._ping_loop_task # Await for the task to finish cancelling
            except asyncio.CancelledError:
                pass # Expected when cancelling the task
            except Exception as e:
                _LOGGER.error(f"Error while stopping ping loop task: {e}")
            self._ping_loop_task = None # Clear the task reference

    async def connect(self):
        """Connect to the Socket.IO server."""

        # Prevent trying to connect if already connected
        if self._is_connected:
            _LOGGER.debug("Already connected, skipping new connection attempt.")
            return True

        # Generate URI
        scheme = "https" if self.use_ssl else "http"
        uri = f"{scheme}://{self.host}:{self.port}"

        connect_kwargs = {}

        # Generate Headers
        headers = {
            'X-Client-Type': 'ha',
            'X-Client-Name': self.client_name
        }
        # 1. If auth_token exists, add Authorization header.
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        connect_kwargs["headers"] = headers

        # 2. Specify Transports
        connect_kwargs["transports"] = ['websocket', 'polling']

        try:
            _LOGGER.info(f"Attempting to connect to Socket.IO server at {uri} with options: {connect_kwargs}")
            await self.sio.connect(uri, **connect_kwargs) # Pass all dynamic arguments
            # Note: The connection will block until connected or an error occurs.
            return True
        except socketio.exceptions.ConnectionError as e:
            _LOGGER.error(f"Socket.IO Connection Error to {uri}: {e}")
            self._is_connected = False
            return False
        except Exception as e:
            _LOGGER.error(f"Unexpected error connecting to Socket.IO {uri}: {e}")
            self._is_connected = False
            return False

    async def disconnect(self):
        """Disconnect from the Socket.IO server."""
        if self._is_connected:
            await self.sio.disconnect()
            _LOGGER.info("Socket.IO client disconnected.")
        self._is_connected = False

    def is_connected(self):
        return self._is_connected

    async def emit(self, event_name, data):
        """Emit an event to the Socket.IO server."""
        if self._is_connected:
            # Save event object
            event_object = dict(data)
            event_object['timestamp'] = datetime.datetime.now()
            event_object['is_valid'] = True
            event_id = event_object.get('id', '__none__')
            self._ha_event_object[event_id] = event_object

            # Emit event to server
            await self.sio.emit(event_name, data)
            _LOGGER.debug(f"Emitted '{event_name}' to Socket.IO server with data: {data}")
        else:
            _LOGGER.warning(f"Cannot emit '{event_name}': Socket.IO client not connected.")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Socket.IO component from a config entry."""
    _LOGGER.debug("Setting up config entry for %s", DOMAIN)

    client_name = entry.data.get("client_name")
    host = entry.data.get("host")
    port = entry.data.get("port")
    use_ssl = entry.data.get("use_ssl", False) # Ensure default is handled
    auth_token = entry.data.get("auth_token")

    hass.data.setdefault(DOMAIN, {})
    socketio_client_wrapper = ICEClientWrapper(hass, client_name, host, port, use_ssl, auth_token)
    hass.data[DOMAIN][entry.entry_id] = socketio_client_wrapper

    # Only attempt to connect once during setup.
    #if not await socketio_client_wrapper.connect():
    #    _LOGGER.warning("Failed to establish initial connection to Socket.IO server.")
    #else:
    #    _LOGGER.info(f"Socket.IO client for {host}:{port} set up successfully.")

    async def _handle_ha_event_to_socketio(event):
        _LOGGER.debug(f"HA event to send to Socket.IO: {event.event_type} - {event.data}")
        await socketio_client_wrapper.emit(
            "event_ha",
            {
                "event": event.event_type,
                "id": str(uuid.uuid4()),
                "data": event.data
            }
        )

    # Register HA Event Listener
    hass.bus.async_listen("ice_event", _handle_ha_event_to_socketio)

    # Register a listener to start background tasks AFTER Home Assistant has fully started
    @callback
    async def _start_background_tasks(event: Event):
        _LOGGER.info("Home Assistant has started. Initiating Socket.IO background tasks.")
        socketio_client_wrapper.start_reconnect_loop()
        socketio_client_wrapper.start_ping_loop()
        socketio_client_wrapper.start_event_result_check_loop()

    # Register a listener to stop background tasks when Home Assistant stops
    @callback
    async def _stop_background_tasks(event: Event):
        _LOGGER.info("Home Assistant is stopping. Stopping Socket.IO background tasks.")
        await socketio_client_wrapper.stop_event_result_check_loop()
        await socketio_client_wrapper.stop_ping_loop()
        await socketio_client_wrapper.stop_reconnect_loop()
        await socketio_client_wrapper.disconnect() # Ensure disconnection as well

    # Add the listener
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _start_background_tasks)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_background_tasks)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry for %s", DOMAIN)

    socketio_client_wrapper = hass.data[DOMAIN].pop(entry.entry_id)
    if socketio_client_wrapper:
        await socketio_client_wrapper.stop_event_result_check_loop()
        await socketio_client_wrapper.stop_reconnect_loop()
        await socketio_client_wrapper.disconnect()

    return True