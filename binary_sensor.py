"""Problem binary sensor for the Zonnepanelen integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ZonnepanelenConfigEntry
from .const import (
    CONF_EXCLUDED_PANELS,
    CONF_UNDERPERFORMANCE_PERCENT,
    DAYLIGHT_ELEVATION_DEG,
    DAYLIGHT_POST_SUNRISE_MINUTES,
    DOMAIN,
    GLOBAL_KEYS,
    MANUFACTURER,
    MAX_MISSING_INVERTERS,
    MIN_MEAN_POWER_FOR_RATIO_CHECK,
    MODEL_ECU,
    UNDERPERFORMANCE_RATIO,
)
from .coordinator import ZonnepanelenDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZonnepanelenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the problem binary sensor."""
    async_add_entities([ZonnepanelenProblemSensor(entry.runtime_data, entry)])


def _in_daylight_window(hass: HomeAssistant) -> bool:
    """Return True during the period in which we expect solar production.

    The window opens once EITHER condition holds:
      - current sun elevation ≥ ``DAYLIGHT_ELEVATION_DEG``, or
      - more than ``DAYLIGHT_POST_SUNRISE_MINUTES`` have passed since today's
        local sunrise.
    The window closes at sunset (elevation < 0 and past solar noon).
    """
    sun_state = hass.states.get("sun.sun")
    if sun_state is not None:
        try:
            elevation = float(sun_state.attributes.get("elevation", 0) or 0)
        except (TypeError, ValueError):
            elevation = 0.0
        if elevation >= DAYLIGHT_ELEVATION_DEG:
            return True
        if elevation < 0:
            # Sun is below the horizon — window closed regardless of
            # the sunrise-offset check.
            return False

    now = dt_util.utcnow()
    today_local = dt_util.as_local(now).date()
    sunrise = get_astral_event_date(hass, SUN_EVENT_SUNRISE, today_local)
    sunset = get_astral_event_date(hass, SUN_EVENT_SUNSET, today_local)
    if sunrise is None or sunset is None:
        # Polar day/night — no useful window. Err on the side of "closed" so
        # we don't spam problem alerts 24/7.
        return False
    return (
        sunrise + timedelta(minutes=DAYLIGHT_POST_SUNRISE_MINUTES)
        <= now
        <= sunset
    )


class ZonnepanelenProblemSensor(
    CoordinatorEntity[ZonnepanelenDataCoordinator], BinarySensorEntity
):
    """Binary sensor that aggregates system-health problems."""

    _attr_has_entity_name = True
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: ZonnepanelenDataCoordinator,
        entry: ZonnepanelenConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_system")},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL_ECU,
            configuration_url=f"http://{coordinator.host}/",
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _excluded_panels(self) -> set[str]:
        """Return the set of panel IDs the user has excluded from checks.

        Read fresh on every call so that changes via the Options flow take
        effect on the next coordinator tick without needing a reload.
        (The entry is reloaded on options change anyway, but this keeps
        the semantics obvious.)
        """
        raw = self._entry.options.get(CONF_EXCLUDED_PANELS, []) or []
        return {str(pid) for pid in raw}

    def _underperformance_ratio(self) -> float:
        """Return the configured underperformance ratio, or the default.

        Stored as a percent int in options; we convert here. Falls back to
        the default on anything unparseable rather than raising — the
        binary sensor should degrade gracefully, not refuse to evaluate.
        """
        raw = self._entry.options.get(CONF_UNDERPERFORMANCE_PERCENT)
        if raw is None:
            return UNDERPERFORMANCE_RATIO
        try:
            pct = int(raw)
        except (TypeError, ValueError):
            return UNDERPERFORMANCE_RATIO
        if not 1 <= pct <= 100:
            return UNDERPERFORMANCE_RATIO
        return pct / 100.0

    def _panel_powers(self) -> dict[str, float]:
        """Return {panel_id: power_W} for panels currently reporting,
        minus any the user has excluded."""
        excluded = self._excluded_panels()
        out: dict[str, float] = {}
        for key, value in self.coordinator.data.items():
            if key in GLOBAL_KEYS or not isinstance(value, dict):
                continue
            if key in excluded:
                continue
            try:
                out[key] = float(value.get("power", 0) or 0)
            except (TypeError, ValueError):
                continue
        return out

    def _reporting_count(self) -> int:
        return len(self._panel_powers())

    def _expected_count(self) -> int:
        """High-water mark of panel count, reduced by any excluded panels
        we've actually seen in the dataset."""
        excluded = self._excluded_panels()
        seen_excluded = sum(
            1
            for key in self.coordinator.data
            if key in excluded and key not in GLOBAL_KEYS
        )
        return max(0, self.coordinator.max_panel_count - seen_excluded)

    def _missing_count(self) -> int:
        return max(0, self._expected_count() - self._reporting_count())

    def _underperforming(self) -> list[str]:
        """Return panel_ids whose power is < ratio × mean-of-others.

        Excluded panels are not candidates and do not contribute to the
        reference mean.
        """
        powers = self._panel_powers()
        if len(powers) < 2:
            return []
        ratio = self._underperformance_ratio()
        total = sum(powers.values())
        bad: list[str] = []
        for pid, power in powers.items():
            others_mean = (total - power) / (len(powers) - 1)
            if others_mean < MIN_MEAN_POWER_FOR_RATIO_CHECK:
                # Not enough production — comparing would just flag shaded
                # panels during morning ramp-up. Spec: gate at 25 W.
                continue
            if power < ratio * others_mean:
                bad.append(pid)
        return bad

    # ── entity API ───────────────────────────────────────────────────────

    @property
    def is_on(self) -> bool | None:
        """True when any problem condition holds."""
        if not self.coordinator.last_update_success:
            # While the ECU is unreachable, don't claim "problem" — the rest
            # of the entities will show as unavailable which is the correct
            # signal. Returning None keeps this sensor out of the user's
            # face during a network blip.
            return None

        daylight = _in_daylight_window(self.hass)
        if daylight and self._missing_count() > MAX_MISSING_INVERTERS:
            return True
        if self._underperforming():
            return True
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        daylight = _in_daylight_window(self.hass)
        missing = self._missing_count()
        under = self._underperforming()
        excluded = self._excluded_panels()
        ratio = self._underperformance_ratio()

        reasons: list[str] = []
        if daylight and missing > MAX_MISSING_INVERTERS:
            reasons.append(f"{missing} inverter(s) not reporting")
        if under:
            reasons.append(
                f"panel(s) producing <{int(ratio * 100)}% "
                f"of others' mean: {', '.join(sorted(under))}"
            )
        return {
            "problem_reasons": reasons,
            "missing_inverter_count": missing,
            "reporting_inverters": self._reporting_count(),
            "expected_inverters": self._expected_count(),
            "underperforming_panels": sorted(under),
            "underperformance_percent": int(ratio * 100),
            "excluded_panels": sorted(excluded),
            "daylight_window_open": daylight,
        }
