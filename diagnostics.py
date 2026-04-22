"""Diagnostics support for the Zonnepanelen integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import ZonnepanelenConfigEntry

# The ECU's local IP/hostname is the user's LAN address. It isn't a secret
# per se, but downloading diagnostics often means sharing them in a GitHub
# issue, so redact by default — matches what other local-polling
# integrations (Envoy, SolarEdge, etc.) do.
_TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the given config entry."""
    coordinator = entry.runtime_data

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "source": entry.source,
            "data": async_redact_data(dict(entry.data), _TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "name": coordinator.name,
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception is not None
            else None,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "max_panel_count": coordinator.max_panel_count,
        },
        "data": coordinator.data,
    }
