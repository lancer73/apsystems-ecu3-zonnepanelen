"""Config flow voor Zonnepanelen integratie."""
import logging
import voluptuous as vol
import urllib.request
import urllib.error

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)


class ZonnepanelenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zonnepanelen."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            name = user_input.get(CONF_NAME, DEFAULT_NAME)
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            # Test connection with host
            try:
                await self.hass.async_add_executor_job(
                    self._test_connection, host
                )
            except Exception as e:
                _LOGGER.error("Connection test failed: %s", e)
                errors["base"] = "cannot_connect"
            else:
                # Create entry
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_NAME: name,
                        CONF_SCAN_INTERVAL: scan_interval,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    def _test_connection(self, host):
        """Test connection with host."""
        errors = []
        
        # Test main page
        try:
            url = f"http://{host}/"
            _LOGGER.debug("Testing connection to main page: %s", url)
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.getcode() != 200:
                    errors.append(f"Invalid response from main page: {response.getcode()}")
                else:
                    content = response.read().decode('utf-8', errors='ignore')
                    if "<tr>" not in content:
                        errors.append("Main page doesn't contain expected content")
        except urllib.error.URLError as e:
            errors.append(f"Connection error to main page: {e}")
        except Exception as e:
            errors.append(f"Error connecting to main page: {e}")
            
        # Test realtime data page
        try:
            url = f"http://{host}/index.php/realtimedata"
            _LOGGER.debug("Testing connection to realtime data page: %s", url)
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.getcode() != 200:
                    errors.append(f"Invalid response from realtime data page: {response.getcode()}")
                else:
                    content = response.read().decode('utf-8', errors='ignore')
                    if "<tr " not in content:
                        errors.append("Realtime data page doesn't contain expected content")
        except urllib.error.URLError as e:
            errors.append(f"Connection error to realtime data page: {e}")
        except Exception as e:
            errors.append(f"Error connecting to realtime data page: {e}")
            
        # If any errors occurred, raise exception
        if errors:
            error_message = "; ".join(errors)
            _LOGGER.error("Connection test failed: %s", error_message)
            raise Exception(error_message)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return ZonnepanelenOptionsFlowHandler(config_entry)


class ZonnepanelenOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Zonnepanelen options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL,
                    self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ),
            ): cv.positive_int,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))
