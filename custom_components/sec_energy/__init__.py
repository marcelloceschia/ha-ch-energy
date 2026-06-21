from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
import aiohttp
import logging
import json

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .config_flow import validate_schema

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SECEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    
    # Register services
    async def handle_validate_url(call: ServiceCall):
        """Handle validate_url service call."""
        url = call.data.get("url")
        if not url:
            return {"success": False, "error": "URL parameter required"}
        
        _LOGGER.info("Validating URL: %s", url)
        
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": "HomeAssistant-SEC-Energy/1.0"}) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    text = await response.text()
                    data = json.loads(text)
                    
                    # Schema validation
                    schema_errors = validate_schema(data)
                    if schema_errors:
                        return {
                            "success": False,
                            "error": "Schema validation failed",
                            "schema_errors": schema_errors,
                            "dso_name": data.get("dsoName", "Unknown"),
                            "tariff_count": len(data.get("tariffs", [])),
                        }
                    
                    # Extract tariff info
                    tariffs = []
                    for t in data.get("tariffs", []):
                        tariffs.append({
                            "name": t.get("tariffName"),
                            "type": t.get("tariffType"),
                            "form": t.get("tariffForm"),
                        })
                    
                    return {
                        "success": True,
                        "dso_name": data.get("dsoName"),
                        "dso_number": data.get("dsoNumber"),
                        "tariff_count": len(tariffs),
                        "tariffs": tariffs,
                    }
                    
        except json.JSONDecodeError as e:
            _LOGGER.error("Invalid JSON from URL: %s", e)
            return {"success": False, "error": f"Invalid JSON: {str(e)}"}
        except aiohttp.ClientError as e:
            _LOGGER.error("HTTP error for URL: %s", e)
            return {"success": False, "error": f"HTTP error: {str(e)}"}
        except Exception as e:
            _LOGGER.error("Unexpected error validating URL: %s", e, exc_info=True)
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    hass.services.async_register(DOMAIN, "validate_url", handle_validate_url)
    _LOGGER.info("Registered service: %s.validate_url", DOMAIN)
    
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
            async with aiohttp.ClientSession(headers={"User-Agent": "HomeAssistant-SEC-Energy/1.0"}) as session:
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
