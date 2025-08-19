import logging
import asyncio
import socketio
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define schema for the user input
DATA_SCHEMA = vol.Schema({
    vol.Required("client_name"): str,
    vol.Required("host"): str,
    vol.Required("port", default=80): int,
    vol.Optional("use_ssl", default=False): bool,
    vol.Optional("auth_token"): str, # Optional authentication token
})

async def test_connection(client_name: str, host: str, port: int, use_ssl: bool = False, auth_token: str = ""):
    sio = socketio.AsyncClient()

    # Generate URI
    scheme = "https" if use_ssl else "http"
    uri = f"{scheme}://{host}:{port}"

    connect_kwargs = {}

    # Generate Headers
    headers = {}

    # 1. If auth_token exists, add Authorization header.
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'

    connect_kwargs["headers"] = headers

    # 2. Specify Transports
    connect_kwargs["transports"] = ['websocket', 'polling']

    connection_timeout = 5 # seconds for connection and message receipt

    try:
        _LOGGER.info(f"Attempting to connect to Socket.IO server at {uri} for connection test...")

        # Connect to the server
        await sio.connect(uri, **connect_kwargs)
        _LOGGER.error("Successfully connected to Socket.IO server.")

        return True, ''

    except socketio.exceptions.ConnectionError as e:
        _LOGGER.error(f"Socket.IO Connection Error to {uri}: {e}")
        return False, str(e) # Return the error message as string

    except asyncio.TimeoutError:
        _LOGGER.error(f"Timed out connecting to Socket.IO server at {uri} after {connection_timeout} seconds.")
        return False, "timeout"

    except Exception as e:
        _LOGGER.error(f"Unexpected error during Socket.IO connection test to {uri}: {e}", exc_info=True)
        return False, str(e)

    finally:
        # Always disconnect to clean up resources
        if sio.connected:
            await sio.disconnect()

class ICEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Your Socket.IO Integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is not None:
            client_name = user_input["client_name"]
            host = user_input["host"]
            port = user_input["port"]
            use_ssl = user_input["use_ssl"]
            auth_token = user_input.get("auth_token")

            # Validate the connection
            test_success = False
            sio_message = 'cannot_connect'
            try:
                _LOGGER.debug(f"Attempting to validate connection...")
                test_success, sio_message = await test_connection(
                    client_name=client_name,
                    host=host,
                    port=port,
                    use_ssl=use_ssl,
                    auth_token=auth_token
                )
            except Exception as e:
                _LOGGER.error("Failed to connect to Socket.IO server: %s", e)
                errors["base"] = "cannot_connect" # Error key for HA frontend
            finally:
                if not test_success:
                    errors["base"] = sio_message # Error key for HA frontend

            if not errors:
                # If validation passes, create a config entry
                return self.async_create_entry(
                    title=f"ICE Server ({host}:{port})",
                    data=user_input, # Store all user input data
                )

        # Show the form to the user
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    # If you need to handle re-configuration (e.g., from Options Flow),
    # you would implement async_step_init and async_step_options
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ICEOptionsFlow(config_entry)

class ICEOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Your Socket.IO Integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Update the config entry with new options
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("client_name", default=self.config_entry.data.get("client_name")): str,
                vol.Required("host", default=self.config_entry.data.get("host")): str,
                vol.Required("port", default=self.config_entry.data.get("port")): int,
                vol.Optional("use_ssl", default=self.config_entry.data.get("use_ssl")): bool,
                vol.Optional("auth_token", default=self.config_entry.data.get("auth_token")): str,
            })
        )