import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_PC_IP, CONF_PC_NAME

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ICE WebSocket Monitor."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL # Or CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Validate user input (e.g., check if IP is valid, though not strictly required for this example)
            pc_ip = user_input[CONF_PC_IP]
            pc_name = user_input.get(CONF_PC_NAME)

            # Check if this PC IP is already configured
            await self.async_set_unique_id(pc_ip)
            self._abort_if_unique_id_configured()

            # Create a config entry
            return self.async_create_entry(
                title=pc_name if pc_name else pc_ip,
                data={
                    CONF_PC_IP: pc_ip,
                    CONF_PC_NAME: pc_name,
                },
            )

        # Show the form to the user
        data_schema = vol.Schema({
            vol.Required(CONF_PC_IP, description={"suggested_value": "192.168.1.100"}): str,
            vol.Optional(CONF_PC_NAME): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        # For this simple integration, we don't need an options flow,
        # but you might implement one if you want to allow editing IP/name later.
        return OptionsFlowHandler()

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for ICE WebSocket Monitor."""

    @property
    def config_entry(self):
        """Initialize options flow."""
        return self.hass.config_entries.async_get_entry(self.handler)

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        return self.async_abort(
            reason="not_supported",
            description_placeholders={
                "message": "현재 이 기기의 옵션 설정은 지원되지 않습니다. 기기를 제거한 후 다시 추가해주세요.",
            }
        )