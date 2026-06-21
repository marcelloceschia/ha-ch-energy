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
        _LOGGER.debug("SECEnergyCoordinator._async_update_data() aufgerufen")
        _LOGGER.debug("URL: %s, Tarif: %s", self.url, self.tariff_name)
        try:
            import json
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    _LOGGER.debug("HTTP Status: %s", response.status)
                    text = await response.text()
                    _LOGGER.debug("Response Länge: %d chars", len(text))
                    data = json.loads(text)
                    _LOGGER.debug("JSON geparst. DSO: %s", data.get('dsoName'))
                    
            # Finde den gewählten Tarif
            tariff = None
            tariffs = data.get("tariffs", [])
            _LOGGER.debug("Suche Tarif '%s' in %d verfügbaren Tarifen", self.tariff_name, len(tariffs))
            for t in tariffs:
                if t["tariffName"] == self.tariff_name:
                    tariff = t
                    break
            
            if not tariff:
                _LOGGER.error("Tarif '%s' nicht gefunden. Verfügbar: %s", self.tariff_name, [t['tariffName'] for t in tariffs])
                raise ValueError(f"Tarif {self.tariff_name} nicht gefunden")
            
            _LOGGER.debug("Tarif gefunden: %s", tariff.get('tariffName'))
            return {"tariff": tariff, "raw": data}
        except Exception as err:
            _LOGGER.error("Fehler beim Laden der Tarifdaten: %s", err, exc_info=True)
            raise
