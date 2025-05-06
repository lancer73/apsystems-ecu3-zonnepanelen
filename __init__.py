"""Zonnepanelen integration for Home Assistant."""
import asyncio
import logging
import re
import urllib.request
import urllib.error
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Zonnepanelen component."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN in config:
        conf = config[DOMAIN]
        host = conf[CONF_HOST]
        name = conf.get(CONF_NAME, DEFAULT_NAME)
        scan_interval = conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        coordinator = ZonnepanelenDataCoordinator(
            hass, host, name, scan_interval
        )

        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][name] = coordinator

        hass.async_create_task(
            hass.helpers.discovery.async_load_platform("sensor", DOMAIN, {"name": name}, config)
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zonnepanelen from a config entry."""
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = ZonnepanelenDataCoordinator(
        hass, host, name, scan_interval
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Error setting up entry: %s", err)
        return False

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class ZonnepanelenDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Zonnepanelen data."""

    def __init__(self, hass, host, name, scan_interval):
        """Initialize the data updater."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.host = host
        self.name = name

    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data via scraping."""
        try:
            return await self.hass.async_add_executor_job(self.fetch_data)
        except urllib.error.URLError as e:
            _LOGGER.warning("Connection to zonnepanelen system failed: %s. Will retry later.", e)
            # Return last data if we have it, otherwise raise an error
            if self.data:
                _LOGGER.info("Using cached data from last successful update")
                return self.data
            raise UpdateFailed(f"Connection failed and no cached data available: {e}")
        except Exception as e:
            _LOGGER.error("Error fetching data: %s", e)
            # Return last data if we have it, otherwise raise an error
            if self.data:
                _LOGGER.info("Using cached data from last successful update")
                return self.data
            raise UpdateFailed(f"Error fetching data: {e}")

    def fetch_data(self) -> Dict[str, Any]:
        """Fetch data from the Zonnepanelen interface."""
        data = {}
        connection_error = None
        timeout = 10  # Timeout in seconds
        
        # Fetch panel details
        try:
            detailpagina = f"http://{self.host}/index.php/realtimedata"
            _LOGGER.debug("Fetching panel details from %s", detailpagina)
            
            with urllib.request.urlopen(detailpagina, timeout=timeout) as readpage:
                getdetails = readpage.read()
                
            lines = re.split('<tr ', str(getdetails))
            panel_count = 0
            
            for line in range(1, len(lines)):
                fields = re.split('<td', str(lines[line]))
                if len(fields) < 2:
                    continue
                    
                panel_id = fields[1][1:15]
                panel_count += 1
                
                data[panel_id] = {}
                try:
                    if len(fields) < 7:
                        data[panel_id]["power"] = fields[2].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                        data[panel_id]["volt"] = fields[3].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                    else:
                        data[panel_id]["power"] = fields[2].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                        data[panel_id]["freq"] = fields[3].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                        data[panel_id]["volt"] = fields[4].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                        data[panel_id]["temp"] = fields[5].split(">", 2)[1].lstrip(' ').split()[0].replace("-", "0", 1)
                except (IndexError, ValueError) as e:
                    _LOGGER.warning("Error parsing panel data for %s: %s", panel_id, e)
                    # Set default values in case of parsing errors
                    if "power" not in data[panel_id]:
                        data[panel_id]["power"] = "0"
                    if "volt" not in data[panel_id]:
                        data[panel_id]["volt"] = "0"
            
            _LOGGER.debug("Found %s panels/inverters", panel_count)
                
        except urllib.error.URLError as e:
            _LOGGER.error("Error connecting to panel details page: %s", e)
            connection_error = e
        except Exception as e:
            _LOGGER.error("Error fetching panel details: %s", e)
        
        # Fetch statistics
        try:
            statistics = f"http://{self.host}/"
            _LOGGER.debug("Fetching statistics from %s", statistics)
            
            with urllib.request.urlopen(statistics, timeout=timeout) as readpage:
                getstats = readpage.read()
                
            lines = re.split('<tr>', str(getstats))
            
            if len(lines) >= 13:  # Ensure we have enough lines
                try:
                    data["lifetime"] = str(re.split('<td>', str(lines[2]))[1]).split()[0]
                    data["state"] = str(re.split('<td>', str(lines[3]))[1]).split()[0]
                    data["day"] = str(re.split('<td>', str(lines[4]))[1]).split()[0]
                    data["online"] = str(re.split('<td>', str(lines[7]))[1]).split('<')[0]
                    data["signal"] = str(re.split('<td>', str(lines[12]))[1]).split('<')[0]
                    
                    # Check if system is online from the state value
                    if data["state"] == "0":
                        _LOGGER.warning("Zonnepanelen system reports offline status (state=0)")
                except (IndexError, ValueError) as e:
                    _LOGGER.warning("Error parsing statistics data: %s", e)
            else:
                _LOGGER.warning("Statistics page has unexpected format, not enough data lines")
        except urllib.error.URLError as e:
            _LOGGER.error("Error connecting to statistics page: %s", e)
            connection_error = e
        except Exception as e:
            _LOGGER.error("Error fetching statistics: %s", e)
        
        # If we have a connection error and no data was collected, raise the error
        if connection_error and not data:
            raise connection_error
            
        # Make sure we have at least some default values if nothing was found
        if not data:
            _LOGGER.warning("No data was collected, using default offline values")
            data = {
                "state": "0",  # 0 indicates offline
                "lifetime": "0",
                "day": "0",
                "online": "0",
                "signal": "0"
            }
        
        _LOGGER.debug("Completed data fetch successfully")
        return data
