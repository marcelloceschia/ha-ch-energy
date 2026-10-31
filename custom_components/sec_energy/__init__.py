from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
import aiohttp
import logging
import json

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .config_flow import validate_schema, PREDEFINED_DSOS, fetch_document
from .sensor import get_current_price
from .tariffs import select_tariff, covers, resolve_document, match_dso
from homeassistant.util import dt as dt_util
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_change

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SECEnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    # Calendar validity changes at local midnight, independently of the fetch interval.
    async def refresh_at_midnight(_now):
        await coordinator.async_request_refresh()

    entry.async_on_unload(async_track_time_change(
        hass, refresh_at_midnight, hour=0, minute=0, second=0))
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

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Persist identity so migration follows the live Jahres-Map catalogue."""
    if entry.version == 1:
        data = dict(entry.data)
        url = data.get("dso_url")
        data.update(dso_key=match_dso(url, PREDEFINED_DSOS),
                    resolved_url=url, valid_until=None)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return entry.version == 2


class SECEnergyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.url = entry.data.get("resolved_url") or entry.data.get("dso_url")
        self.tariff_name = entry.data.get("tariff", "S-Standard")
        self.dso_name = entry.data.get("dso_name", "SEC Energy")
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.tariffs")
        self._cache = None
        self._cache_loaded = False
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
        )

    def record_current_price(self, price):
        """Persist observed current prices; forecast queries never call this."""
        if price is None or self.data is None or self.data.get("last_price") == price:
            return
        self.data["last_price"] = price
        if self._cache is not None:
            self._cache["last_price"] = price
            # HA Store coalesces same-loop reads and flushes pending writes on shutdown.
            self._store.async_delay_save(lambda: dict(self._cache or {}), 0)

    async def _fetch_document(self, url):
        return await fetch_document(url)

    async def _async_update_data(self):
        day = dt_util.now().date()
        if not self._cache_loaded:
            self._cache = await self._store.async_load()
            self._cache_loaded = True
        key = self.entry.data.get("dso_key")
        source = PREDEFINED_DSOS.get(key, self.entry.data.get("dso_url"))
        failed = False
        try:
            url, document = await resolve_document(
                source, day, self._fetch_document, validate_schema, self.tariff_name)
            self.url = url
            active = select_tariff(document, self.tariff_name, day)
            # Q4 prefetch must not replace today's prices with next year's.
            if active is None and self._cache:
                active = select_tariff(self._cache["raw"], self.tariff_name, day)
                active = active or self._cache.get("tariff")
            result = {"raw": document, "tariff": active, "resolved_url": url,
                      "last_price": (self._cache or {}).get("last_price")}
            if self._cache and active == self._cache.get("tariff"):
                result["tariff_url"] = self._cache.get("tariff_url", self._cache.get("resolved_url"))
            else:
                result["tariff_url"] = url
            self._cache = result
            await self._store.async_save(result)
            selected = select_tariff(document, self.tariff_name, day)
            if selected is None:
                selected = next(t for t in document["tariffs"] if
                                t.get("tariffName") == self.tariff_name and
                                covers(t, day.replace(year=day.year + 1, month=1, day=1)))
            updated = {**self.entry.data, "resolved_url": url, "valid_until": selected.get("endDate")}
            if updated != self.entry.data:
                self.hass.config_entries.async_update_entry(self.entry, data=updated)
        except (OSError, ValueError, TypeError, aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("No current tariff source for %s: %s", self.dso_name, err)
            failed = True
            if not self._cache:
                # No known price: do not invent one from an expired/future document.
                result = {"raw": {}, "tariff": None, "resolved_url": self.url, "tariff_url": None}
            else:
                result = dict(self._cache)
                # Cached two-year documents remain usable across New Year.
                result["tariff"] = select_tariff(result["raw"], self.tariff_name, day) or result.get("tariff")
        active = result.get("tariff") or {}
        expired = failed or not active or not covers(active, day)
        last_price = (self.data or {}).get("last_price")
        if last_price is None and self._cache:
            last_price = self._cache.get("last_price")
        if active and covers(active, day):
            last_price = get_current_price(active, dt_util.now())
        result = {**result, "last_price": last_price, "data_expired": expired,
                  "valid_from": active.get("startDate"), "valid_until": active.get("endDate")}
        if self._cache is not None:
            self._cache["last_price"] = last_price
            await self._store.async_save(self._cache)
        issue_id = f"tariff_expired_{self.entry.entry_id}"
        if expired:
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id, is_fixable=False,
                severity=ir.IssueSeverity.WARNING, translation_key="tariff_expired",
                translation_placeholders={"dso": self.dso_name,
                                          "valid_until": str(result["valid_until"] or "unknown")})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        return result
