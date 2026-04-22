# Zonnepanelen — APsystems ECU-3 for Home Assistant
 
Home Assistant integration that monitors a local **APsystems ECU-3**
solar energy communication unit. It polls the ECU's built-in web
interface over HTTP on your LAN — no cloud account, no internet
required, no credentials stored.
 
Tested against Home Assistant 2025.5 – 2026.4.
 
## What it does
 
- Discovers every microinverter reported by the ECU and creates an
  entity per electrical measurement it exposes.
- Exposes the system-wide totals from the ECU's index page.
- Adds an aggregated health **problem** binary sensor so you can alert
  on missing or underperforming inverters without wiring up a template
  yourself.
- Supports *reconfigure* (change the ECU's IP when your router reshuffles
  the DHCP lease) and *diagnostics download* for easy bug reports.
### Entities
 
System device (one per ECU):
 
| Entity | Description |
|---|---|
| `sensor.<name>_current_power` | System power, W |
| `sensor.<name>_daily_energy` | Energy produced today, kWh |
| `sensor.<name>_lifetime_energy` | Cumulative energy, kWh |
| `sensor.<name>_online_inverters` | Number of inverters the ECU currently sees |
| `sensor.<name>_signal_strength` | ECU ↔ inverter signal, raw value from the ECU (typically 0–5, bars) |
| `binary_sensor.<name>_problem` | See *Problem detection* below |
 
Per-panel device (one per microinverter, linked to the system device):
 
| Entity | Description |
|---|---|
| `sensor.<name>_panel_<id>_power` | Instantaneous output, W |
| `sensor.<name>_panel_<id>_voltage` | AC voltage, V |
| `sensor.<name>_panel_<id>_frequency` | Grid frequency, Hz (if reported) |
| `sensor.<name>_panel_<id>_temperature` | Inverter temperature, °C (if reported) |
 
`lifetime_energy` and `daily_energy` are suitable for the Energy
Dashboard out of the box.
 
### Problem detection
 
`binary_sensor.<name>_problem` turns on when **any** of the following
holds:
 
1. **Missing inverters during daylight.** More than two fewer inverters
   are reporting than at the session's peak, AND we're inside the
   daylight window — defined as *sun elevation ≥ 10°* OR *more than 60
   minutes past today's local sunrise* (and before sunset). This avoids
   alarms during a normal sunrise ramp-up.
2. **Underperforming panel.** Any panel is producing less than 25% of
   the mean of the others, gated on that mean being at least 25 W (so
   morning ramp-up and overcast conditions don't generate noise).
The sensor returns *unknown* while the ECU is unreachable, so it
doesn't false-fire during a brief network outage.
 
Useful attributes (for dashboards and automations):
 
- `problem_reasons` — human-readable list of what's wrong right now.
- `missing_inverter_count`, `reporting_inverters`, `expected_inverters`.
- `underperforming_panels` — list of panel IDs currently below the ratio.
- `daylight_window_open` — whether the missing-inverter check is active.
## Requirements
 
- Home Assistant ≥ 2025.5.
- An APsystems **ECU-3** that's reachable from your HA host over HTTP on
  port 80, with its web interface enabled.
- HACS (optional but recommended for updates).
## Installation
 
### Via HACS (recommended)
 
The integration is **not in the default HACS index**. Add the GitHub
repository as a HACS *custom repository*:
 
1. Open **HACS** in Home Assistant.
2. Click the **⋮ menu** (top-right) → **Custom repositories**.
3. Paste the repository URL:
   `https://github.com/lancer73/apsystems-ecu3-zonnepanelen`
   Category: **Integration**. Click **Add**.
4. Find **Zonnepanelen (APsystems ECU-3)** in the HACS integrations
   list and click **Download**.
5. **Restart Home Assistant.**
6. Go to **Settings → Devices & Services → Add Integration** and search
   for **Zonnepanelen**.
### Manual
 
1. Copy the `custom_components/zonnepanelen/` directory from this
   repository into `<config>/custom_components/` on your HA instance so
   you end up with `<config>/custom_components/zonnepanelen/`.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Zonnepanelen.**
## Configuration
 
Everything is configured through the UI — there is no YAML schema.
 
During the config flow:
 
- **Host** — your ECU's LAN IP or hostname (without `http://` and
  without a path). Example: `192.168.1.42`.
- **Name** — the device name HA will display. Defaults to
  `Zonnepanelen`.
- **Update interval** — seconds between polls, between 30 and 3600.
  Defaults to 300.
The integration probes the ECU's `/` and `/index.php/realtimedata`
endpoints during setup and refuses to create the entry if either fails.
 
### Reconfiguring
 
If the ECU moves to a new IP or you want to change the scan interval
without losing history:
 
1. **Settings → Devices & Services → Zonnepanelen → ⋮ menu →
   Reconfigure.**
2. Enter the new host/interval.
History, statistics and Energy Dashboard wiring are preserved because
the config entry (and therefore all entity IDs) stays the same. The
flow will refuse to point an existing entry at a *different* ECU —
remove the entry and add a new one if that's what you want.
 
### Changing just the scan interval
 
Open the integration's **Configure** button (options flow) to change
the poll interval without going through reconfigure.
 
## Diagnostics
 
**Settings → Devices & Services → Zonnepanelen → Download diagnostics**
produces a JSON blob with entry metadata, coordinator state, and the
last parsed dataset from the ECU. The ECU's host is redacted by
default, since diagnostics dumps are usually shared in public GitHub
issues.
 
## Networking & security
 
- All communication is **local HTTP** on port 80. The ECU-3 doesn't
  offer HTTPS or authentication; this is consistent with other local
  solar integrations (Envoy, SolarEdge local API, …).
- HA talks to the ECU directly — no data leaves your LAN.
- HTTP requests time out at 10 seconds.
- No credentials are stored anywhere. The host field accepts hostnames
  and IPv4/IPv6 literals only; full URLs are rejected.
## Known limitations
 
- The ECU's web interface occasionally returns an empty or malformed
  page. The integration keeps the previous poll's data, flips every
  entity to *unavailable*, and retries on the next tick — no stale
  "fresh-looking" readings.
- The problem sensor's *expected inverter count* is an in-memory
  high-water mark that resets when HA restarts. After a restart the
  missing-inverter check needs one successful poll before it can fire.
- New panels added to the ECU are picked up on the next coordinator
  refresh; no reload required.
- Parsing is regex-based against the ECU-3's HTML. A firmware update
  that changes the page layout will break parsing. File an issue with a
  diagnostics download attached if this happens.
## Migration & upgrade notes
 
Entity `unique_id`s changed from `zonnepanelen_<…>` to entry-ID-scoped
values in v2.0.0. The migration is automatic — history, statistics and
Energy Dashboard wiring survive.
 
v2.0.0 had a bug where old device records were left behind as empty
orphans after the migration. v2.1.1 adds a follow-up migration that
removes those orphans automatically on the first HA restart after
upgrade.
 
Any automations that addressed the old devices **by `device_id`** need
re-pointing — either at the new device or (preferably) at the entities
by `entity_id`.
 
## Troubleshooting
 
- **"Failed to connect" during setup.** Check you can reach
  `http://<host>/` and `http://<host>/index.php/realtimedata` from the
  HA host (e.g. `curl`). If your HA host is in a separate VLAN from
  the ECU, allow TCP/80.
- **Everything is unavailable.** Check the *Logs* for
  `Zonnepanelen (<host>): UpdateFailed` — if it's
  `ECU unreachable` the ECU is down or on a different IP (use the
  Reconfigure flow). If it's `ECU returned no parseable data`, attach
  a diagnostics download to an issue.
- **Problem sensor fires every morning.** The daylight window starts
  at 10° sun elevation OR 60 minutes past sunrise — if your site is
  heavily shaded at that time, the underperformance check can pick up
  legitimately-dim panels. You can suppress the automation using the
  `daylight_window_open` attribute or by gating on a sun-elevation
  condition.
## Credits
 
Originally written by [@lancer73](https://github.com/lancer73). The
ECU-3 web scraping is inspired by a community Python script referenced
in the original repository.
 
## License
 
See `LICENSE` in the repository root.
