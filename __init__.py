"""Zonnepanelen (APsystems ECU-3) integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, GLOBAL_KEYS
from .coordinator import ZonnepanelenDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

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


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ZonnepanelenConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Control whether a user may delete a device from the UI.

    Returns True (the "Delete" button appears) only when none of the
    device's Zonnepanelen identifiers match a currently-reporting ECU
    component — i.e. the device is an orphan (pre-1.0.0 leftover, a panel
    that has been physically removed, etc.). Active system and panel
    devices are protected: deleting them at random would drop their
    area/name/disabled-state customisations and cause HA to immediately
    re-create them on the next coordinator refresh.
    """
    coordinator = config_entry.runtime_data
    entry_id = config_entry.entry_id

    # Build the set of identifiers that correspond to things the ECU is
    # currently reporting. The system device is always considered "live"
    # while the entry is loaded — if the ECU is unreachable the
    # coordinator will already have flipped its entities unavailable and
    # the user can reconfigure instead of deleting.
    live_identifiers: set[str] = {f"{entry_id}_system"}
    data = coordinator.data or {}
    for key, value in data.items():
        if key in GLOBAL_KEYS or not isinstance(value, dict):
            continue
        live_identifiers.add(f"{entry_id}_{key}")

    # Refuse deletion if any of the device's Zonnepanelen identifiers
    # matches a live component.
    for domain, ident in device_entry.identifiers:
        if domain == DOMAIN and ident in live_identifiers:
            return False

    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: ZonnepanelenConfigEntry
) -> bool:
    """Migrate a config entry from an older version.

    v1 → v2: rewrite entity ``unique_id`` values and device identifiers to
        include the config entry ID. The old scheme was ``zonnepanelen_<key>``
        device identifiers and ``zonnepanelen_<key>_<key>`` unique_ids; both
        could collide across multiple ECU instances.
    v2 → v3: clean up orphaned old-style devices left behind by v2.0.0, which
        only migrated entity unique_ids (not device identifiers). The original
        ``(DOMAIN, "system")`` / ``(DOMAIN, <panel_id>)`` device records stayed
        in the registry without any entities attached.
    """
    _LOGGER.debug(
        "Migrating Zonnepanelen entry from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    entry_id = entry.entry_id

    if entry.version == 1:
        # --- Entity unique_id migration -------------------------------------
        @callback
        def _migrate_entity(
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

        await er.async_migrate_entries(hass, entry_id, _migrate_entity)

        # --- Device identifier migration -----------------------------------
        # The v2.0.0 release missed this step, which left future upgraders
        # in an inconsistent state (old empty device records + new device
        # records carrying all the entities). Doing it here during v1→v2
        # means a fresh upgrade from v1 never sees that state — the device
        # records are renamed in place and the entities re-attach to them
        # when the platforms set up.
        dev_reg = dr.async_get(hass)
        for device in list(
            dr.async_entries_for_config_entry(dev_reg, entry_id)
        ):
            new_identifiers: set[tuple[str, str]] = set()
            changed = False
            for domain, ident in device.identifiers:
                if domain == DOMAIN and not ident.startswith(f"{entry_id}_"):
                    new_identifiers.add((domain, f"{entry_id}_{ident}"))
                    changed = True
                else:
                    new_identifiers.add((domain, ident))
            if changed:
                _LOGGER.info(
                    "Migrating device identifiers for %s: %s → %s",
                    device.name or device.id,
                    device.identifiers,
                    new_identifiers,
                )
                dev_reg.async_update_device(
                    device.id, new_identifiers=new_identifiers
                )

        hass.config_entries.async_update_entry(entry, version=2)

    if entry.version == 2:
        # v2 → v3: for users upgrading from 2.0.0, the device identifier
        # migration above never ran. Their entities are already attached to
        # new-style devices (created automatically by HA when 2.0.0's sensors
        # came up). The old-style device records remain as empty orphans.
        # Remove any device under this entry whose identifiers are all
        # old-style and carry no entities.
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        for device in list(
            dr.async_entries_for_config_entry(dev_reg, entry_id)
        ):
            # Classify the device's Zonnepanelen identifiers.
            zp_idents = [
                ident
                for (domain, ident) in device.identifiers
                if domain == DOMAIN
            ]
            if not zp_idents:
                continue
            is_old_style = all(
                not ident.startswith(f"{entry_id}_") for ident in zp_idents
            )
            if not is_old_style:
                continue

            # Only remove if no entities are left pinned to this device.
            # (They shouldn't be — the unique_id migration in v2.0.0 caused
            # them to re-attach to new-style devices — but be defensive.)
            linked = er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            )
            if linked:
                _LOGGER.warning(
                    "Old-style device %s still has %s entities attached; "
                    "leaving it in place to avoid data loss",
                    device.name or device.id,
                    len(linked),
                )
                continue

            _LOGGER.info(
                "Removing orphaned old-style device %s (identifiers=%s)",
                device.name or device.id,
                device.identifiers,
            )
            dev_reg.async_remove_device(device.id)

        hass.config_entries.async_update_entry(entry, version=3)

    _LOGGER.debug("Migration to version %s complete", entry.version)
    return True
