from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
import aiohttp
import logging

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SECEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class SECEnergyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.url = entry.data.get("dso_url")
        self.tariff_name = entry.data.get("tariff", "S-Standard")
        self.dso_name = entry.data.get("dso_name", "SEC Energy")
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
        )

    async def _async_update_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    data = await response.json()
                    
            # Finde den gewählten Tarif
            tariff = None
            for t in data.get("tariffs", []):
                if t["tariffName"] == self.tariff_name:
                    tariff = t
                    break
            
            if not tariff:
                raise ValueError(f"Tarif {self.tariff_name} nicht gefunden")
            
            return {"tariff": tariff, "raw": data}
        except Exception as err:
            _LOGGER.error("Fehler beim Laden der Tarifdaten: %s", err)
            raise
