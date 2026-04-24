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
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_EXCLUDED_PANELS,
    CONF_ILLUMINANCE_ENTITY,
    CONF_MIN_ILLUMINANCE,
    CONF_MIN_MISSING_INVERTERS,
    CONF_UNDERPERFORMANCE_PERCENT,
    DEFAULT_MIN_ILLUMINANCE,
    DEFAULT_MIN_MISSING_INVERTERS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GLOBAL_KEYS,
    MAX_MIN_ILLUMINANCE,
    MAX_MIN_MISSING_INVERTERS,
    MAX_SCAN_INTERVAL,
    MAX_UNDERPERFORMANCE_PERCENT,
    MIN_MIN_ILLUMINANCE,
    MIN_MIN_MISSING_INVERTERS,
    MIN_SCAN_INTERVAL,
    MIN_UNDERPERFORMANCE_PERCENT,
    REQUEST_TIMEOUT,
    UNDERPERFORMANCE_RATIO,
)
from .coordinator import validate_host

_LOGGER = logging.getLogger(__name__)

_SCAN_INTERVAL_SELECTOR = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
)

_UNDERPERFORMANCE_SELECTOR = vol.All(
    vol.Coerce(int),
    vol.Range(
        min=MIN_UNDERPERFORMANCE_PERCENT, max=MAX_UNDERPERFORMANCE_PERCENT
    ),
)

_MIN_MISSING_INVERTERS_SELECTOR = vol.All(
    vol.Coerce(int),
    vol.Range(min=MIN_MIN_MISSING_INVERTERS, max=MAX_MIN_MISSING_INVERTERS),
)

_MIN_ILLUMINANCE_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_MIN_ILLUMINANCE,
        max=MAX_MIN_ILLUMINANCE,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="lx",
    )
)

_ILLUMINANCE_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class="illuminance")
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

# Reconfigure only exposes the fields the user might realistically change on
# an existing entry — host (e.g. ECU moved to a new IP) and scan interval.
# The title/name is an identity property and is stable.
STEP_RECONFIGURE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
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

    VERSION = 3

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry.

        Users can change the host (e.g. the ECU moved to a new LAN IP) and
        the scan interval without having to remove and re-add the
        integration, which would also lose statistics history.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                host = validate_host(user_input[CONF_HOST])
            except ValueError:
                errors["base"] = "invalid_host"
            else:
                # Allow the user to keep the same host (no-op) but block
                # reusing *another* entry's host.
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                self._abort_if_unique_id_configured()
                try:
                    await _async_test_connection(self.hass, host)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001 — last-resort for UI feedback
                    _LOGGER.exception("Unexpected error probing ECU")
                    errors["base"] = "unknown"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_HOST: host,
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL,
                                entry.data.get(
                                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                                ),
                            ),
                        },
                    )

        # Pre-fill with the entry's current values.
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=entry.data.get(CONF_HOST, "")
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=entry.data.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): _SCAN_INTERVAL_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
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
            # The illuminance entity selector returns "" when the field is
            # cleared. Normalise to a missing key so the rest of the code
            # can treat "not configured" as a single case.
            if user_input.get(CONF_ILLUMINANCE_ENTITY) in ("", None):
                user_input.pop(CONF_ILLUMINANCE_ENTITY, None)
                # If the entity was cleared, drop the companion lux
                # threshold too — it has no meaning without an entity.
                user_input.pop(CONF_MIN_ILLUMINANCE, None)
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_excluded: list[str] = list(
            self.config_entry.options.get(CONF_EXCLUDED_PANELS, []) or []
        )
        current_percent = int(
            self.config_entry.options.get(
                CONF_UNDERPERFORMANCE_PERCENT,
                int(UNDERPERFORMANCE_RATIO * 100),
            )
        )
        current_min_missing = int(
            self.config_entry.options.get(
                CONF_MIN_MISSING_INVERTERS, DEFAULT_MIN_MISSING_INVERTERS
            )
        )
        current_lux_entity = self.config_entry.options.get(
            CONF_ILLUMINANCE_ENTITY, ""
        )
        current_min_lux = float(
            self.config_entry.options.get(
                CONF_MIN_ILLUMINANCE, DEFAULT_MIN_ILLUMINANCE
            )
        )

        # Union of panel IDs currently reporting + already-excluded,
        # so the user can un-exclude a panel even while it's offline.
        coordinator = self.config_entry.runtime_data
        reporting: set[str] = set()
        if coordinator is not None and coordinator.data:
            for key, value in coordinator.data.items():
                if key in GLOBAL_KEYS or not isinstance(value, dict):
                    continue
                reporting.add(str(key))

        panel_ids = sorted(reporting.union(current_excluded))
        panel_options = [
            SelectOptionDict(value=pid, label=pid) for pid in panel_ids
        ]

        # Only expose the panel selector when there's at least one option —
        # an empty multi-select renders as a confusing dead UI element.
        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_SCAN_INTERVAL, default=current_interval
            ): _SCAN_INTERVAL_SELECTOR,
            vol.Optional(
                CONF_MIN_MISSING_INVERTERS, default=current_min_missing
            ): _MIN_MISSING_INVERTERS_SELECTOR,
            vol.Optional(
                CONF_UNDERPERFORMANCE_PERCENT, default=current_percent
            ): _UNDERPERFORMANCE_SELECTOR,
            vol.Optional(
                CONF_ILLUMINANCE_ENTITY, default=current_lux_entity
            ): _ILLUMINANCE_ENTITY_SELECTOR,
            vol.Optional(
                CONF_MIN_ILLUMINANCE, default=current_min_lux
            ): _MIN_ILLUMINANCE_SELECTOR,
        }
        if panel_options:
            schema_dict[
                vol.Optional(
                    CONF_EXCLUDED_PANELS, default=current_excluded
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=panel_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    custom_value=False,
                )
            )

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict)
        )
