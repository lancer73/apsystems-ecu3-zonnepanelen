"""Sensor platform for the Zonnepanelen integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZonnepanelenConfigEntry
from .const import DOMAIN, GLOBAL_KEYS, MANUFACTURER, MODEL_ECU, MODEL_INVERTER
from .coordinator import ZonnepanelenDataCoordinator

_LOGGER = logging.getLogger(__name__)

# Device classes whose state must be numeric.
_NUMERIC_DEVICE_CLASSES = frozenset(
    {
        SensorDeviceClass.ENERGY,
        SensorDeviceClass.POWER,
        SensorDeviceClass.VOLTAGE,
        SensorDeviceClass.FREQUENCY,
        SensorDeviceClass.TEMPERATURE,
    }
)

PANEL_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="power",
        translation_key="panel_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="volt",
        translation_key="panel_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="freq",
        translation_key="panel_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="temp",
        translation_key="panel_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

GLOBAL_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="state",
        translation_key="system_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="lifetime",
        translation_key="lifetime_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="day",
        translation_key="daily_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="online",
        translation_key="online_inverters",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="signal",
        translation_key="signal_strength",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZonnepanelenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []

    for description in GLOBAL_SENSOR_TYPES:
        if description.key in coordinator.data:
            entities.append(
                ZonnepanelenSystemSensor(coordinator, entry, description)
            )

    for panel_id, panel_data in coordinator.data.items():
        if panel_id in GLOBAL_KEYS or not isinstance(panel_data, dict):
            continue
        for description in PANEL_SENSOR_TYPES:
            if description.key in panel_data:
                entities.append(
                    ZonnepanelenPanelSensor(
                        coordinator, entry, description, panel_id
                    )
                )

    async_add_entities(entities)


class _ZonnepanelenBaseSensor(
    CoordinatorEntity[ZonnepanelenDataCoordinator], SensorEntity
):
    """Shared behaviour for all Zonnepanelen sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZonnepanelenDataCoordinator,
        entry: ZonnepanelenConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialise a sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry.entry_id

    def _coerce(self, value: Any) -> Any:
        """Cast the raw value to float when the device class requires it."""
        if self.entity_description.device_class in _NUMERIC_DEVICE_CLASSES:
            try:
                return float(value)
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "Non-numeric value %r for %s", value, self.entity_id
                )
                return None
        return value


class ZonnepanelenSystemSensor(_ZonnepanelenBaseSensor):
    """Sensor representing the ECU system as a whole."""

    def __init__(
        self,
        coordinator: ZonnepanelenDataCoordinator,
        entry: ZonnepanelenConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_system")},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL_ECU,
            configuration_url=f"http://{coordinator.host}/",
        )

    @property
    def native_value(self) -> Any:
        return self._coerce(self.coordinator.data.get(self.entity_description.key))


class ZonnepanelenPanelSensor(_ZonnepanelenBaseSensor):
    """Sensor for an individual panel / microinverter."""

    def __init__(
        self,
        coordinator: ZonnepanelenDataCoordinator,
        entry: ZonnepanelenConfigEntry,
        description: SensorEntityDescription,
        panel_id: str,
    ) -> None:
        super().__init__(coordinator, entry, description)
        self._panel_id = panel_id
        self._attr_translation_placeholders = {"panel_id": panel_id}
        self._attr_unique_id = (
            f"{entry.entry_id}_{panel_id}_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{panel_id}")},
            name=f"Panel {panel_id}",
            manufacturer=MANUFACTURER,
            model=MODEL_INVERTER,
            via_device=(DOMAIN, f"{entry.entry_id}_system"),
        )

    @property
    def native_value(self) -> Any:
        panel = self.coordinator.data.get(self._panel_id)
        if not isinstance(panel, dict):
            return None
        return self._coerce(panel.get(self.entity_description.key))

    @property
    def available(self) -> bool:
        # ``super().available`` already reflects the coordinator's
        # ``last_update_success`` — if the ECU is unreachable the entity is
        # unavailable regardless of what the last cached ``data`` says.
        if not super().available:
            return False
        # The ECU reports state == "0" when the whole system is offline; there
        # is no usable per-panel reading in that case.
        if self.coordinator.data.get("state") == "0":
            return False
        # The panel must be present in the most recent update. When a panel
        # drops out of the ECU's output (removed, offline for long enough that
        # the ECU stops reporting it), the entity becomes unavailable instead
        # of showing stale values.
        return isinstance(self.coordinator.data.get(self._panel_id), dict)
