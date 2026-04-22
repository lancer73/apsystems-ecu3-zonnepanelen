# Zonnepanelen integration — 2026.4 compatibility review
 
Target: Home Assistant 2025.5 → 2026.4. Delivered as a drop-in replacement
under `custom_components/zonnepanelen/`. Current version: **2.1.2**.
 
## v2.1.2 — signal-strength unit reverted
 
The v2.0.0 rewrite added `native_unit_of_measurement=PERCENTAGE` to the
signal-strength sensor on the assumption that the ECU-3 reports signal
as 0–100 %. The original integration declared no unit at all and simply
displayed the raw string scraped from the ECU's index page. The field's
meaning is firmware-dependent (some firmwares report bars, others a
percentage), and adding a unit the ECU doesn't guarantee was a bug.
v2.1.2 removes the unit (and the `MEASUREMENT` state class, since the
value is an opaque string and would fail statistics validation). Behaviour
now matches the pre-2.0.0 sensor. If your firmware does report a true
percentage, add it back via a Template sensor with the appropriate unit.
 
## v2.1.1 — orphaned-device cleanup
 
Bug in 2.0.0: the v1 → v2 migration rewrote entity `unique_id`s but did
*not* rewrite device identifiers. After upgrade, entities re-attached to
freshly-created new-identifier devices, leaving the original device
records behind as empty orphans (same symptom: "entities grouped under
new devices, old devices stayed behind with nothing attached"). 2.1.1
fixes both paths:
 
- Config entry version bumped `2 → 3`.
- **v1 → v2** migration now also rewrites device identifiers in place
  (old-style `(DOMAIN, "system")` / `(DOMAIN, <panel_id>)` →
  `(DOMAIN, "{entry_id}_system")` / `(DOMAIN, "{entry_id}_{panel_id}")`).
  Users coming straight from v1 never see the orphaned state.
- **v2 → v3** migration detects old-style device records under the entry,
  checks they have no entities attached, and removes them. This is the
  fix for anyone who already upgraded to 2.0.0/2.1.0 and is now looking
  at empty old devices in the UI. The migration is defensive — if an
  old-style device still has entities pinned to it for any reason, it
  logs a warning and leaves the device alone rather than deleting entity
  history.
Note: device_ids on the new-style devices differ from the old ones.
Automations that addressed the old devices by `device_id` will not find
them — but those automations were already broken after 2.0.0, because
the old devices had no entities. Automations addressing entities by
`entity_id` (the common case) keep working.
 
## v2.1.0 additions
 
- **Problem binary sensor** (`binary_sensor.py`) — single aggregated health
  entity with `device_class = PROBLEM`. Fires when:
  1. The ECU is reporting more than two fewer inverters than the
     per-session high-water mark, **and** we're within the daylight window
     (sun elevation ≥ 10° OR more than 60 minutes past today's local
     sunrise, and before sunset).
  2. One or more panels produce less than 25% of the mean of the others,
     gated on that mean being ≥ 25 W (avoids false positives during morning
     ramp-up and on cloudy days).
  Exposes `problem_reasons`, `missing_inverter_count`,
  `reporting_inverters`, `expected_inverters`, `underperforming_panels`,
  `daylight_window_open` as state attributes. Returns `None` (unknown)
  while the coordinator is failing to reach the ECU, so it doesn't fire
  false alerts during a WAN/LAN blip.
- **Reconfigure flow** (`config_flow.py::async_step_reconfigure`) — change
  the ECU's IP address or the scan interval without removing and re-adding
  the integration. History and statistics are preserved because the config
  entry (and therefore entity IDs) stays the same. Uses HA 2024.12+
  helpers (`_get_reconfigure_entry`, `async_update_reload_and_abort`).
- **Diagnostics** (`diagnostics.py`) — `Download diagnostics` button on the
  integration's entry returns entry metadata, coordinator state
  (last_update_success, last_exception, update interval, expected-panel
  high-water mark) and the last parsed dataset. `CONF_HOST` is redacted
  by default — consistent with other local-polling integrations — because
  diagnostics dumps are commonly pasted into public GitHub issues.
- **Problem-detection thresholds** added to `const.py`:
  `MAX_MISSING_INVERTERS=2`, `UNDERPERFORMANCE_RATIO=0.25`,
  `MIN_MEAN_POWER_FOR_RATIO_CHECK=25.0`, `DAYLIGHT_ELEVATION_DEG=10.0`,
  `DAYLIGHT_POST_SUNRISE_MINUTES=60`.
- Coordinator now tracks a per-session **high-water mark of reporting
  panels** (`max_panel_count`) so the problem sensor can detect
  inverters that dropped out. Resets on HA restart — documented
  limitation.
## Files changed
 
- `manifest.json` — version bumped to `2.1.0`
- `const.py` — rewritten (added constants, host limits, `GLOBAL_KEYS`,
  problem-detection thresholds)
- `coordinator.py` — **new** (extracted from `__init__.py`); adds
  `max_panel_count` high-water mark
- `__init__.py` — rewritten (YAML setup removed; uses `runtime_data`);
  `PLATFORMS` now includes `BINARY_SENSOR`
- `config_flow.py` — rewritten (removed deprecated patterns); adds
  `async_step_reconfigure`
- `sensor.py` — rewritten
- `binary_sensor.py` — **new** (problem sensor)
- `diagnostics.py` — **new**
- `strings.json`, `translations/en.json`, `translations/nl.json` — updated
  with entity translations, new error/abort keys, reconfigure step, and
  the `problem` binary sensor
## HA breaking changes addressed
 
| Change | Impact | Fix |
|---|---|---|
| `DataUpdateCoordinator` must receive `config_entry` (stops working 2025.11) | Would fail on startup | `super().__init__(..., config_entry=entry)` in `coordinator.py` |
| `OptionsFlow` setting `self.config_entry` explicitly (stops working 2025.12) | Deprecation warning → breakage | Removed the `__init__`; HA injects `config_entry` automatically; also removed passing `config_entry` to the constructor |
| `async_forward_entry_setup` (singular) deprecated, removed 2025.6 | Not used in original — kept plural form |
| `hass.helpers.*` deprecated, being removed | Original used `hass.helpers.discovery.async_load_platform` | Removed along with the YAML setup path |
| YAML configuration for config-flow integrations discouraged | Original mixed YAML and UI setup | Dropped YAML (`async_setup` removed); doc updated |
| `CONN_CLASS_LOCAL_POLL` deprecated since 2021.6 | Noise in logs | Removed |
| `ConfigEntry.runtime_data` is the current pattern for per-entry state | `hass.data[DOMAIN][entry_id]` still works, but runtime_data is typed and auto-cleaned | Switched; `__init__.py` declares `type ZonnepanelenConfigEntry = ConfigEntry[ZonnepanelenDataCoordinator]` |
| `_attr_has_entity_name = True` is Bronze-tier baseline | Old entities had ad-hoc names | All entities set `has_entity_name=True`, names come from `translation_key` |
| `DeviceInfo` dataclass over dict | Dict still works but is untyped | Switched; also added `configuration_url`, `manufacturer`, `model`, `via_device` |
| `AddEntitiesCallback` → `AddConfigEntryEntitiesCallback` | Current entry-scoped callback | Updated |
 
## Failure-mode behaviour (post-fix)
 
- **ECU unreachable / DNS fail / connection refused** → `aiohttp.ClientError`
  caught in coordinator, raised as `UpdateFailed`. Coordinator preserves
  `self.data`, flips `last_update_success = False`. Every entity's
  `available` goes to `False`. After recovery the next successful update
  restores them. No stale "fresh-looking" readings.
- **ECU times out** → `TimeoutError` caught, same path as above.
- **ECU returns HTTP 5xx/4xx** → `raise_for_status` raises
  `ClientResponseError` (a `ClientError`), same path.
- **Missing inverter in ECU output** → panel is absent from
  `coordinator.data`; `available` returns `False` and `native_value`
  returns `None`. HA's default write-on-every-update behaviour means the
  UI flips promptly. When the panel reappears, it becomes available again
  on the next update. (New panels require a reload/re-add to get
  entities — documented limitation.)
- **System offline (`state == "0"`)** → all panel sensors return
  `available = False`; system sensors keep their values so you can see
  that the ECU itself is still reachable and reporting offline.
- **Partial parse failure** → if the stats page parses but `realtimedata`
  doesn't (or vice versa), whichever side succeeded is returned; the other
  side's entities go unavailable. If both fail, `UpdateFailed` is raised.
- **First refresh fails** → `async_config_entry_first_refresh` converts
  `UpdateFailed` to `ConfigEntryNotReady`; HA retries with exponential
  backoff, as expected.
- **Duplicate entry (same host)** → `async_set_unique_id(host.lower())` +
  `_abort_if_unique_id_configured` aborts the flow.
- **Non-UTF-8 bytes in response** → `resp.text(errors="replace")` tolerates.
## Other bugs fixed
 
- `sensor.py:async_setup_platform` referenced an undefined `config_entry`
  variable. That code path is gone (YAML setup removed).
- `unique_id` was `"zonnepanelen_<panel>_<key>"` — not unique across multiple
  ECU instances. Now prefixed with `entry_id`. **Note:** this changes
  existing entity IDs; see "Migration" below.
- Signal strength sensor now declares `%` as its unit.
- Panel availability no longer returns `False` forever when `state == "0"`
  *and* we have cached data — the fallback re-use of last-good data now
  covers brief network blips without dropping entities.
## Security review findings
 
Concerns are low but worth listing:
 
1. **HTTP, no auth, no TLS.** The ECU-3 exposes a cleartext HTTP interface
   with no authentication. On a home LAN this is the norm. Nothing to fix
   here — documenting it.
2. **Input validation on host field.** Previously accepted anything
   including `http://...` with path, which would then produce odd URLs.
   Now validated with a regex; rejects schemes and path separators.
3. **No sensitive data logged.** `_LOGGER.debug` logs URLs (host included)
   — acceptable. No credentials exist.
4. **Timeouts.** All HTTP calls use `aiohttp.ClientTimeout(total=10)`.
5. **Fragile HTML scraping.** Regex-based parsing is brittle but out of
   scope; parsing failures now degrade gracefully (fall back to last data,
   log, surface `UpdateFailed` only when no cache).
6. **Unique-id collisions.** Addressed above.
7. **Dependencies.** `manifest.json` declares none, so no supply-chain
   surface beyond HA itself.
## Seamless entity migration
 
The config flow version is bumped from `1` → `2`. On first load after the
update, `async_migrate_entry` runs `entity_registry.async_migrate_entries`
and rewrites every old `unique_id` in place:
 
- System sensors: `zonnepanelen_<key>_<key>` → `<entry_id>_<key>`
- Panel sensors: `zonnepanelen_<panel_id>_<desc>` → `<entry_id>_<panel_id>_<desc>`
Because HA keys entities by `unique_id`, this means entity IDs, history,
statistics, Energy dashboard references, and automations continue to work
untouched. No user action required. Rollback is not supported (migrations
are one-way) — standard HA behaviour.
 
## Brand image
 
Added `brand/icon.png` (256×256) and `brand/icon@2x.png` (512×512), plus
`logo.png` / `logo@2x.png`. Ships a stylised sun + angled solar panel on
a transparent background; picks up automatically in HA 2026.3+ for custom
integrations with in-repo brand images. For HA versions before 2026.3 the
brand image is ignored (no harm), and you can still submit the same PNGs
to `home-assistant/brands` if you want the icon to appear on older versions.
 
## Not done
 
- **Tests.** None existed; not in scope.
- **Dark-mode brand variants** (`dark_icon.png`, `dark_logo.png`). The
  current icon has enough contrast on both themes, but HA does support
  dedicated dark variants if you want a tuned look.
- **Persistent expected-inverter count.** `max_panel_count` is in-memory
  only and resets on HA restart, so "missing inverter" detection takes one
  successful poll after restart before it can fire. Persisting to
  `Store` would avoid this but adds write traffic on every update; deemed
  not worth it for a local-polling integration that restarts infrequently.
