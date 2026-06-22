from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_point_in_time
from datetime import datetime, timedelta
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

WEEKDAY_MAP = {0: "Mo", 1: "Tu", 2: "We", 3: "Th", 4: "Fr", 5: "Sa", 6: "Su"}
MONTH_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

# Price category thresholds (relative to tariff structure)
PRICE_CATEGORIES = {
    "cheap": {"label": "Günstig"},
    "normal": {"label": "Normal"},
    "expensive": {"label": "Hochtarif"},
    "peak": {"label": "Spitzenpreis"},
}


def get_price_category(price, all_prices):
    """Determine price category based on relative position in tariff prices.
    
    Args:
        price: Current price to categorize
        all_prices: List of all possible prices in the tariff
    
    Returns:
        dict with category, color, label, percentile
    """
    if not all_prices or len(all_prices) < 2:
        return {"category": "normal", **PRICE_CATEGORIES["normal"], "percentile": 50}
    
    sorted_prices = sorted(all_prices)
    min_price = sorted_prices[0]
    max_price = sorted_prices[-1]
    
    # Calculate percentile (0-100)
    if max_price == min_price:
        percentile = 50
    else:
        percentile = ((price - min_price) / (max_price - min_price)) * 100
    
    # Determine category based on percentile
    if percentile < 25:
        cat = "cheap"
    elif percentile < 50:
        cat = "normal"
    elif percentile < 75:
        cat = "expensive"
    else:
        cat = "peak"
    
    return {
        "category": cat,
        "label": PRICE_CATEGORIES[cat]["label"],
        "percentile": round(percentile, 1)
    }


def get_all_prices(tariff):
    """Extract all unique energy prices from a tariff for comparison.
    
    Args:
        tariff: The tariff dictionary from API
    
    Returns:
        List of unique prices (floats)
    """
    prices = set()
    price_list = tariff.get("prices", {}).get("energy", [])
    for item in price_list:
        if "price" in item:
            prices.add(float(item["price"]))
    return sorted(list(prices))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Main sensors (with DSO name)
    main_sensors = [
        SECEnergyPriceSensor(coordinator, entry),
        SECEnergyForecastSensor(coordinator, entry),
        SECEnergyBasePriceSensor(coordinator, entry),
    ]
    
    # Alias sensors (short, generic names)
    alias_sensors = [
        SECEnergyPriceAlias(coordinator, entry),
        SECEnergyForecastAlias(coordinator, entry),
        SECEnergyBasePriceAlias(coordinator, entry),
        SECEnergyIsHighTariffAlias(coordinator, entry),
        SECEnergyNextHourAlias(coordinator, entry),
        SECEnergyLowestTodayAlias(coordinator, entry),
        SECEnergyHighestTodayAlias(coordinator, entry),
    ]
    
    async_add_entities(main_sensors + alias_sensors)


class SECEnergyBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._sensor_type}"
        # Verwende den Namen aus dem Entry oder den DSO-Namen als Fallback
        name = entry.data.get("name") or coordinator.dso_name or "SEC Energy"
        self._attr_name = f"{name} {self._sensor_name}"
        # Device Info für Gruppierung
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name,
            "manufacturer": coordinator.dso_name or "SEC Energy",
            "model": entry.data.get("tariff", "Unknown"),
        }

    @property
    def available(self):
        return self.coordinator.last_update_success


# ============================================================================
# MAIN SENSORS (with DSO name prefix)
# ============================================================================

class SECEnergyPriceSensor(SECEnergyBaseSensor):
    _sensor_type = "current_price"
    _sensor_name = "Aktueller Preis"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self):
        _LOGGER.debug("SECEnergyPriceSensor.native_value() aufgerufen")
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            _LOGGER.warning("Kein Tarif in coordinator.data vorhanden")
            return None
        price = get_current_price(tariff, datetime.now())
        _LOGGER.debug("Aktueller Preis: %s CHF/kWh", price)
        return price

    @property
    def extra_state_attributes(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return {}
        prices = tariff.get("prices", {})
        base = prices.get("base", {})
        return {
            "tariff_name": tariff.get("tariffName"),
            "tariff_type": tariff.get("tariffType"),
            "base_price_monthly": base.get("price"),
            "base_price_unit": base.get("priceUnit"),
        }


class SECEnergyForecastSensor(SECEnergyBaseSensor):
    _sensor_type = "forecast"
    _sensor_name = "Preisvorhersage"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:chart-line"

    @property
    def native_value(self):
        _LOGGER.debug("SECEnergyForecastSensor.native_value() aufgerufen")
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            _LOGGER.warning("Kein Tarif in coordinator.data vorhanden")
            return None
        price = get_current_price(tariff, datetime.now())
        _LOGGER.debug("Forecast aktueller Preis: %s CHF/kWh", price)
        _LOGGER.info("FORECAST_SENSOR: Tarif=%s, Preis=%s", tariff.get("tariffName", "unknown"), price)
        return price

    @property
    def extra_state_attributes(self):
        _LOGGER.debug("SECEnergyForecastSensor.extra_state_attributes() aufgerufen")
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            _LOGGER.warning("Kein Tarif für Forecast vorhanden")
            return {}
        
        # Get all possible prices for category calculation
        all_prices = get_all_prices(tariff)
        
        now = datetime.now()
        forecast = []
        for i in range(25):
            future = now + timedelta(hours=i)
            future_hour = future.replace(minute=0, second=0, microsecond=0)
            if future_hour < now.replace(minute=0, second=0, microsecond=0):
                future_hour += timedelta(hours=1)
            price = get_current_price(tariff, future_hour)
            category = get_price_category(price, all_prices)
            forecast.append({
                "hour": future_hour.isoformat(),
                "price": price,
                "price_unit": "CHF/kWh",
                "category": category["category"],
                "category_label": category["label"],
                "percentile": category["percentile"]
            })
        
        _LOGGER.debug("Forecast generiert: %d Einträge", len(forecast))
        return {"forecast": forecast}


class SECEnergyBasePriceSensor(SECEnergyBaseSensor):
    _sensor_type = "base_price"
    _sensor_name = "Grundgebühr"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_native_unit_of_measurement = "CHF/Monat"
        self._attr_icon = "mdi:cash"

    @property
    def native_value(self):
        _LOGGER.debug("SECEnergyBasePriceSensor.native_value() aufgerufen")
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            _LOGGER.warning("Kein Tarif für Grundgebühr vorhanden")
            return None
        prices = tariff.get("prices", {})
        base = prices.get("base", {})
        value = base.get("price", 0)
        _LOGGER.debug("Grundgebühr: %s %s", value, base.get("priceUnit", ""))
        return value


# ============================================================================
# ALIAS SENSORS (short, generic names - for easy use in dashboards)
# ============================================================================

class SECEnergyTimeAwareAlias(CoordinatorEntity, SensorEntity):
    """Base class for alias sensors that need updates at tariff boundaries.

    Automatically schedules state updates at the next tariff change time.
    """

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._next_change_unsub = None

    async def async_added_to_hass(self):
        """When entity is added to hass, schedule next tariff change."""
        await super().async_added_to_hass()
        self._schedule_next_tariff_change()

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        self._schedule_next_tariff_change()

    def _schedule_next_tariff_change(self):
        """Calculate and schedule update at next tariff boundary."""
        if self._next_change_unsub:
            self._next_change_unsub()
            self._next_change_unsub = None

        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return

        next_change = get_next_tariff_change(tariff, datetime.now())
        if next_change:
            _LOGGER.debug(
                "%s: Next tariff change at %s",
                self._attr_name,
                next_change.isoformat(),
            )
            self._next_change_unsub = async_track_point_in_time(
                self.hass, self._on_tariff_change, next_change
            )

    @callback
    def _on_tariff_change(self, _now):
        """Called at tariff boundary — force state refresh."""
        _LOGGER.debug("%s: Tariff boundary reached, updating state", self._attr_name)
        self._next_change_unsub = None
        self.async_write_ha_state()
        self._schedule_next_tariff_change()

    async def async_will_remove_from_hass(self):
        """Cleanup scheduled tariff change when entity is removed."""
        if self._next_change_unsub:
            self._next_change_unsub()
            self._next_change_unsub = None
        await super().async_will_remove_from_hass()


class SECEnergyPriceAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_aktuell"""
    _sensor_type = "alias_current_price"
    _sensor_name = "Strompreis Aktuell"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_current_price"
        self._attr_name = "Strompreis Aktuell"
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        return get_current_price(tariff, datetime.now())

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyForecastAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_forecast"""
    _sensor_type = "alias_forecast"
    _sensor_name = "Strompreis Forecast"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_forecast"
        self._attr_name = "Strompreis Forecast"
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:chart-line"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        return get_current_price(tariff, datetime.now())

    @property
    def extra_state_attributes(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return {}
        
        # Get all possible prices for category calculation
        all_prices = get_all_prices(tariff)
        
        now = datetime.now()
        forecast = []
        for i in range(25):
            future = now + timedelta(hours=i)
            future_hour = future.replace(minute=0, second=0, microsecond=0)
            if future_hour < now.replace(minute=0, second=0, microsecond=0):
                continue
            price = get_current_price(tariff, future_hour)
            cat = get_price_category(price, all_prices)
            forecast.append({
                "hour": future_hour.isoformat(),
                "price": price,
                "category": cat["category"],
                "label": cat["label"],
            })
        
        return {"forecast": forecast}

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyBasePriceAlias(CoordinatorEntity, SensorEntity):
    """Alias sensor: sensor.strompreis_grundgebuehr"""
    _sensor_type = "alias_base_price"
    _sensor_name = "Strompreis Grundgebühr"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_alias_base_price"
        self._attr_name = "Strompreis Grundgebühr"
        self._attr_native_unit_of_measurement = "CHF/Monat"
        self._attr_icon = "mdi:cash"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        prices = tariff.get("prices", {})
        base = prices.get("base", {})
        return base.get("price", 0)

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyIsHighTariffAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_ist_hochtarif
    
    Dynamically determines if current price is the high tariff rate
    by comparing current price against all prices in the tariff.
    Schedules updates at exact tariff change times.
    """
    _sensor_type = "alias_is_high_tariff"
    _sensor_name = "Strompreis Ist Hochtarif"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_is_high_tariff"
        self._attr_name = "Strompreis Ist Hochtarif"
        self._attr_icon = "mdi:clock-time-eight-outline"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        
        now = datetime.now()
        current_price = get_current_price(tariff, now)
        
        # Collect all unique prices from the tariff
        prices = tariff.get("prices", {})
        energy_tiers = prices.get("energy", [])
        
        if not energy_tiers:
            return "false"
        
        # Get all unique prices
        all_prices = set()
        for tier in energy_tiers:
            all_prices.add(tier.get("price", 0))
        
        if not all_prices:
            return "false"
        
        max_price = max(all_prices)
        
        # If current price equals max price, it's high tariff
        if current_price >= max_price:
            return "true"
        return "false"

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyNextHourAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_naechste_stunde"""
    _sensor_type = "alias_next_hour"
    _sensor_name = "Strompreis Nächste Stunde"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_next_hour"
        self._attr_name = "Strompreis Nächste Stunde"
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_icon = "mdi:arrow-right"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        next_hour = datetime.now() + timedelta(hours=1)
        return get_current_price(tariff, next_hour)

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyLowestTodayAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_tiefster_heute"""
    _sensor_type = "alias_lowest_today"
    _sensor_name = "Strompreis Tiefster Heute"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_lowest_today"
        self._attr_name = "Strompreis Tiefster Heute"
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_icon = "mdi:arrow-down-bold"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        
        now = datetime.now()
        prices = []
        for hour in range(24):
            dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            prices.append(get_current_price(tariff, dt))
        
        return min(prices) if prices else None

    @property
    def available(self):
        return self.coordinator.last_update_success


class SECEnergyHighestTodayAlias(SECEnergyTimeAwareAlias):
    """Alias sensor: sensor.strompreis_hoechster_heute"""
    _sensor_type = "alias_highest_today"
    _sensor_name = "Strompreis Höchster Heute"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alias_highest_today"
        self._attr_name = "Strompreis Höchster Heute"
        self._attr_native_unit_of_measurement = "CHF/kWh"
        self._attr_icon = "mdi:arrow-up-bold"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name") or coordinator.dso_name or "SEC Energy",
        }

    @property
    def native_value(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        
        now = datetime.now()
        prices = []
        for hour in range(24):
            dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            prices.append(get_current_price(tariff, dt))
        
        return max(prices) if prices else None

    @property
    def available(self):
        return self.coordinator.last_update_success


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_price(tariff, dt):
    weekday = WEEKDAY_MAP[dt.weekday()]
    month = MONTH_MAP[dt.month]
    prices = tariff.get("prices", {})
    energy_tiers = prices.get("energy", [])
    
    for tier in energy_tiers:
        if month not in tier.get("months", []):
            continue
        if weekday not in tier.get("weekdays", []):
            continue
        if time_in_range(tier["from"], tier["to"], dt):
            return tier["price"]
    
    if energy_tiers:
        return min(tier["price"] for tier in energy_tiers)
    return 0.0


def time_in_range(from_time, to_time, check_time):
    from_h, from_m = map(int, from_time.split(":"))
    to_h, to_m = map(int, to_time.split(":"))
    check_min = check_time.hour * 60 + check_time.minute
    from_min = from_h * 60 + from_m
    if to_h == 0 and to_m == 0:
        to_min = 24 * 60
    else:
        to_min = to_h * 60 + to_m
    if from_min <= to_min:
        return from_min <= check_min < to_min
    return check_min >= from_min or check_min < to_min


def get_next_tariff_change(tariff, now):
    """Calculate the next time when the tariff price changes.

    Examines all energy tiers and finds the next from/to boundary
    that is strictly after the current time.

    Returns:
        datetime of next change, or None if no change found.
    """
    prices = tariff.get("prices", {})
    energy_tiers = prices.get("energy", [])
    if not energy_tiers:
        return None

    weekday = WEEKDAY_MAP[now.weekday()]
    month = MONTH_MAP[now.month]

    # Collect all time boundaries (from and to) for tiers that apply today
    boundaries = set()
    for tier in energy_tiers:
        if month not in tier.get("months", []):
            continue
        if weekday not in tier.get("weekdays", []):
            continue
        boundaries.add(tier["from"])
        boundaries.add(tier["to"])

    if not boundaries:
        return None

    # Find the next boundary after current time
    current_min = now.hour * 60 + now.minute
    next_min = None

    for boundary in boundaries:
        h, m = map(int, boundary.split(":"))
        boundary_min = h * 60 + m
        # Skip boundaries that are exactly now or in the past
        if boundary_min <= current_min:
            continue
        if next_min is None or boundary_min < next_min:
            next_min = boundary_min

    # If no boundary found today, the next change is at midnight (00:00 tomorrow)
    if next_min is None:
        next_change = datetime(now.year, now.month, now.day, 0, 0) + timedelta(days=1)
    else:
        next_change = datetime(now.year, now.month, now.day, next_min // 60, next_min % 60)

    return next_change
