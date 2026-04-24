"""DataUpdateCoordinator for the Zonnepanelen integration."""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, GLOBAL_KEYS, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# Accept RFC 1123 hostnames and IPv4/IPv6 literals. This is intentionally
# conservative: we only want to reject obviously-malformed values that could
# break URL construction or indicate user confusion (e.g. pasting a full URL).
_HOST_RE = re.compile(
    r"^(?!https?://)"                 # no scheme
    r"(?!.*/)"                        # no path separators
    r"[A-Za-z0-9_.\-:\[\]]+$"         # hostname, IPv4, or bracketed IPv6
)


def validate_host(host: str) -> str:
    """Return a normalised host or raise ValueError.

    Rejects inputs that look like full URLs or contain path components.
    """
    host = (host or "").strip()
    if not host:
        raise ValueError("empty host")
    if not _HOST_RE.match(host):
        raise ValueError(f"invalid host: {host!r}")
    return host


class ZonnepanelenDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch data from the APsystems ECU-3 web interface."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        host: str,
        scan_interval: int,
    ) -> None:
        """Initialise the coordinator.

        Passing ``config_entry`` explicitly is required as of Home Assistant
        2025.11 (the coordinator emits a deprecation warning otherwise).
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({host})",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=config_entry,
        )
        self.host: str = host
        self._session: ClientSession = async_get_clientsession(hass)
        self._timeout = ClientTimeout(total=REQUEST_TIMEOUT)
        # High-water mark of the number of panels the ECU has reported during
        # this HA session. Used by the problem binary sensor to detect
        # missing inverters. Resets on HA restart — see CHANGES.md for the
        # known-limitation note.
        self.max_panel_count: int = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the ECU and parse the HTML pages.

        Any connection/timeout error is raised as ``UpdateFailed``. The
        coordinator preserves ``self.data`` across failed updates but flips
        ``last_update_success`` to ``False``, which propagates to every
        entity's ``available`` — the correct signal for "ECU down".
        Silently returning cached data would leave entities reporting stale
        values as if fresh.
        """
        try:
            realtime_html = await self._fetch(
                f"http://{self.host}/index.php/realtimedata"
            )
            stats_html = await self._fetch(f"http://{self.host}/")
        except TimeoutError as err:
            raise UpdateFailed(f"ECU timed out: {err}") from err
        except (ClientError, OSError) as err:
            raise UpdateFailed(f"ECU unreachable: {err}") from err

        data: dict[str, Any] = {}
        self._parse_panel_details(realtime_html, data)
        self._parse_statistics(stats_html, data)

        if not data:
            raise UpdateFailed("ECU returned no parseable data")

        # Update the high-water mark. We only ever grow it — dropping panels
        # is precisely the failure mode we want the problem sensor to detect.
        panel_count = sum(
            1
            for key, value in data.items()
            if key not in GLOBAL_KEYS and isinstance(value, dict)
        )
        if panel_count > self.max_panel_count:
            self.max_panel_count = panel_count

        return data

    async def _fetch(self, url: str) -> str:
        """Perform an HTTP GET and return decoded text."""
        _LOGGER.debug("Fetching %s", url)
        async with self._session.get(url, timeout=self._timeout) as resp:
            resp.raise_for_status()
            # ECU pages are effectively ASCII; fall back to latin-1 for stray
            # bytes rather than letting the whole update fail.
            return await resp.text(encoding="utf-8", errors="replace")

    @staticmethod
    def _parse_panel_details(html: str, data: dict[str, Any]) -> None:
        """Parse the /index.php/realtimedata HTML page."""
        lines = re.split(r"<tr ", html)
        panels = 0

        for raw in lines[1:]:
            fields = re.split(r"<td", raw)
            if len(fields) < 2:
                continue

            panel_id = fields[1][1:15]
            panels += 1
            entry: dict[str, Any] = {}

            try:
                if len(fields) < 7:
                    entry["power"] = _first_number(fields[2])
                    entry["volt"] = _first_number(fields[3])
                else:
                    entry["power"] = _first_number(fields[2])
                    entry["freq"] = _first_number(fields[3])
                    entry["volt"] = _first_number(fields[4])
                    entry["temp"] = _first_number(fields[5])
            except (IndexError, ValueError) as err:
                _LOGGER.warning("Unparseable panel row for %s: %s", panel_id, err)
                entry.setdefault("power", "0")
                entry.setdefault("volt", "0")

            data[panel_id] = entry

        _LOGGER.debug("Parsed %s panels", panels)

    @staticmethod
    def _parse_statistics(html: str, data: dict[str, Any]) -> None:
        """Parse the / (index) HTML page."""
        lines = re.split(r"<tr>", html)
        if len(lines) < 13:
            _LOGGER.warning(
                "Statistics page has unexpected format (%s rows)", len(lines)
            )
            return

        try:
            data["lifetime"] = _td_value(lines[2])
            data["state"] = _td_value(lines[3])
            data["day"] = _td_value(lines[4])
            data["online"] = _td_text(lines[7])
            data["signal"] = _td_text(lines[12])
        except (IndexError, ValueError) as err:
            _LOGGER.warning("Unparseable statistics row: %s", err)
            return

        if data.get("state") == "0":
            _LOGGER.info("ECU reports system state offline (state=0)")


def _first_number(field: str) -> str:
    """Extract the first whitespace-separated token from an HTML <td> fragment."""
    body = field.split(">", 2)[1].lstrip(" ").split()[0]
    return body.replace("-", "0", 1)


def _td_value(line: str) -> str:
    """Return the first whitespace-separated token of a <td>-containing line."""
    return re.split(r"<td>", line)[1].split()[0]


def _td_text(line: str) -> str:
    """Return the text before the first '<' inside a <td>-containing line."""
    return re.split(r"<td>", line)[1].split("<")[0]
