"""Zonnepanelen (APsystems ECU-3) integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, GLOBAL_KEYS
from .coordinator import ZonnepanelenDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Typed ConfigEntry alias — makes ``entry.runtime_data`` properly typed.
# (See Home Assistant developer blog, "Store runtime data inside the config entry".)
type ZonnepanelenConfigEntry = ConfigEntry[ZonnepanelenDataCoordinator]

# Panel sensor description keys that used to appear as the suffix of old
# unique_ids. Used only by the migration below.
_PANEL_KEYS: frozenset[str] = frozenset({"power", "volt", "freq", "temp"})


async def async_setup_entry(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> bool:
    """Set up Zonnepanelen from a config entry."""
    host: str = entry.data[CONF_HOST]
    # Scan interval may live in options (changed via Options flow) or in data
    # (set at initial configuration). Options wins when present.
    scan_interval: int = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = ZonnepanelenDataCoordinator(
        hass, entry, host, scan_interval
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> bool:
    """Migrate a config entry from an older version.

    v1 → v2: rewrite entity ``unique_id`` values to include the config entry
    ID. The old scheme was ``zonnepanelen_<key>_<key>`` for system sensors and
    ``zonnepanelen_<panel_id>_<key>`` for panel sensors; both could collide if
    more than one ECU was set up and were not tied to the config entry.
    """
    _LOGGER.debug(
        "Migrating Zonnepanelen entry from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    if entry.version == 1:
        entry_id = entry.entry_id

        @callback
        def _migrate(
            registry_entry: er.RegistryEntry,
        ) -> dict[str, str] | None:
            old = registry_entry.unique_id

            # System sensors: "zonnepanelen_<key>_<key>", key ∈ GLOBAL_KEYS.
            for key in GLOBAL_KEYS:
                if old == f"{DOMAIN}_{key}_{key}":
                    new = f"{entry_id}_{key}"
                    _LOGGER.info("Migrating unique_id %s → %s", old, new)
                    return {"new_unique_id": new}

            # Panel sensors: "zonnepanelen_<panel_id>_<desc_key>" where
            # desc_key ∈ {power, volt, freq, temp}. Panel IDs are 14 chars in
            # practice but we don't rely on that — we split from the right by
            # the known suffix set.
            prefix = f"{DOMAIN}_"
            if old.startswith(prefix):
                rest = old[len(prefix):]
                for desc_key in _PANEL_KEYS:
                    suffix = f"_{desc_key}"
                    if rest.endswith(suffix):
                        panel_id = rest[: -len(suffix)]
                        if panel_id and panel_id not in GLOBAL_KEYS:
                            new = f"{entry_id}_{panel_id}_{desc_key}"
                            _LOGGER.info(
                                "Migrating unique_id %s → %s", old, new
                            )
                            return {"new_unique_id": new}

            return None

        await er.async_migrate_entries(hass, entry_id, _migrate)

        hass.config_entries.async_update_entry(entry, version=2)

    _LOGGER.debug("Migration to version %s complete", entry.version)
    return True
