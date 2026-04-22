"""Config and options flow for the Zonnepanelen integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import ClientError, ClientTimeout
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
)
from .coordinator import validate_host

_LOGGER = logging.getLogger(__name__)

_SCAN_INTERVAL_SELECTOR = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): _SCAN_INTERVAL_SELECTOR,
    }
)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect to the ECU."""


class InvalidHost(HomeAssistantError):
    """Error to indicate the supplied host is malformed."""


async def _async_test_connection(hass: HomeAssistant, host: str) -> None:
    """Probe the ECU's two endpoints. Raises CannotConnect on failure."""
    session = async_get_clientsession(hass)
    timeout = ClientTimeout(total=REQUEST_TIMEOUT)

    for path, marker in (("/", "<tr>"), ("/index.php/realtimedata", "<tr ")):
        url = f"http://{host}{path}"
        try:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding="utf-8", errors="replace")
        except (ClientError, TimeoutError, OSError) as err:
            _LOGGER.debug("Probe failed for %s: %s", url, err)
            raise CannotConnect(f"cannot reach {url}: {err}") from err

        if marker not in text:
            raise CannotConnect(f"{url} did not return the expected content")


class ZonnepanelenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Zonnepanelen."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                host = validate_host(user_input[CONF_HOST])
            except ValueError:
                errors["base"] = "invalid_host"
            else:
                # Prevent the same ECU being configured twice.
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()

                try:
                    await _async_test_connection(self.hass, host)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001 — last-resort for UI feedback
                    _LOGGER.exception("Unexpected error probing ECU")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, DEFAULT_NAME),
                        data={
                            CONF_HOST: host,
                            CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:  # noqa: ARG004
        """Create the options flow.

        Home Assistant injects ``config_entry`` onto the options flow instance
        automatically (since 2024.12); we must NOT assign it ourselves — that
        pattern stops working in Home Assistant 2025.12.
        """
        return ZonnepanelenOptionsFlow()


class ZonnepanelenOptionsFlow(OptionsFlow):
    """Handle the options flow for Zonnepanelen."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=current
                ): _SCAN_INTERVAL_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
