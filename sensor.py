"""Support for Zonnepanelen sensors."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZonnepanelenDataCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_SENSOR_TYPES = [
    SensorEntityDescription(
        key="power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="volt",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="freq",
        name="Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="temp",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]

GLOBAL_SENSOR_TYPES = [
    SensorEntityDescription(
        key="state",
        name="State",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="lifetime",
        name="Lifetime Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="day",
        name="Daily Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="online",
        name="Online Inverters",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="signal",
        name="Signal Strength",
        state_class=SensorStateClass.MEASUREMENT,
    ),
]


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the Zonnepanelen sensor platform."""
    if discovery_info is None:
        return

    name = discovery_info["name"]
    coordinator = hass.data[DOMAIN][name]

    entities = []

    # Add global sensors
    for sensor_description in GLOBAL_SENSOR_TYPES:
        if sensor_description.key in coordinator.data:
            entities.append(
                ZonnepanelenSensor(
                    coordinator,
                    coordinator.name,
                    sensor_description,
                    sensor_description.key,
                )
            )

    # Add panel-specific sensors
    for panel_id, panel_data in coordinator.data.items():
        if panel_id not in ["state", "lifetime", "day", "online", "signal"]:
            for sensor_description in PANEL_SENSOR_TYPES:
                if sensor_description.key in panel_data:
                    entities.append(
                        ZonnepanelenSensor(
                            coordinator,
                            f"{config_entry.title} {panel_id}",
                            sensor_description,
                            panel_id,
                            sensor_description.key,
                        )
                    )

    async_add_entities(entities)


class ZonnepanelenSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Zonnepanelen sensor."""

    def __init__(
        self,
        coordinator,
        name,
        description,
        panel_id,
        data_key=None,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._panel_id = panel_id
        self._data_key = data_key or panel_id
        self._attr_name = f"{name} {description.name}"
        self._attr_unique_id = f"{DOMAIN}_{panel_id}_{self._data_key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        try:
            if self._data_key in ["state", "lifetime", "day", "online", "signal"]:
                value = self.coordinator.data.get(self._data_key, "0")
                # Convert to float for numerical sensors
                if self.entity_description.device_class in [
                    SensorDeviceClass.ENERGY,
                    SensorDeviceClass.POWER,
                    SensorDeviceClass.VOLTAGE,
                    SensorDeviceClass.FREQUENCY,
                    SensorDeviceClass.TEMPERATURE,
                ]:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        _LOGGER.warning("Unable to convert %s to float", value)
                        return 0.0
                return value
            else:
                value = self.coordinator.data.get(self._panel_id, {}).get(self._data_key, "0")
                # Convert to float for numerical sensors
                if self.entity_description.device_class in [
                    SensorDeviceClass.ENERGY,
                    SensorDeviceClass.POWER,
                    SensorDeviceClass.VOLTAGE,
                    SensorDeviceClass.FREQUENCY,
                    SensorDeviceClass.TEMPERATURE,
                ]:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        _LOGGER.warning("Unable to convert %s to float", value)
                        return 0.0
                return value
        except Exception as e:
            _LOGGER.error("Error determining native value for %s: %s", self._attr_name, e)
            return None
            
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # First check if coordinator is available
        if not self.coordinator.last_update_success:
            return False
            
        # If it's a system-level sensor, always return availability based on coordinator
        if self._data_key in ["lifetime", "day", "online", "signal"]:
            return True
            
        # For 'state' sensor, always available to show system status
        if self._data_key == "state":
            return True
            
        # For panel-specific sensors, check if system is online (state != 0)
        system_state = self.coordinator.data.get("state", "0")
        if system_state == "0":
            return False
            
        # Check if this specific panel has data
        if self._panel_id not in self.coordinator.data:
            return False
            
        return True

    @property
    def device_info(self):
        """Return device information."""
        if self._data_key in ["state", "lifetime", "day", "online", "signal"]:
            return {
                "identifiers": {(DOMAIN, "system")},
                "name": f"{self.coordinator.name} System",
                "manufacturer": "Zonnepanelen",
            }
        
        return {
            "identifiers": {(DOMAIN, self._panel_id)},
            "name": f"{self.coordinator.name} {self._panel_id}",
            "manufacturer": "Zonnepanelen",
            "via_device": (DOMAIN, "system"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Zonnepanelen sensor platform from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    # Add global sensors
    for sensor_description in GLOBAL_SENSOR_TYPES:
        if sensor_description.key in coordinator.data:
            entities.append(
                ZonnepanelenSensor(
                    coordinator,
                    f"{config_entry.title}",
                    sensor_description,
                    sensor_description.key,
                )
            )

    # Add panel-specific sensors
    for panel_id, panel_data in coordinator.data.items():
        if panel_id not in ["state", "lifetime", "day", "online", "signal"]:
            for sensor_description in PANEL_SENSOR_TYPES:
                if sensor_description.key in panel_data:
                    entities.append(
                        ZonnepanelenSensor(
                            coordinator,
                            f"{coordinator.name} {panel_id}",
                            sensor_description,
                            panel_id,
                            sensor_description.key,
                        )
                    )

    async_add_entities(entities)
