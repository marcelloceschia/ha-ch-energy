from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timedelta
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

WEEKDAY_MAP = {0: "Mo", 1: "Tu", 2: "We", 3: "Th", 4: "Fr", 5: "Sa", 6: "Su"}
MONTH_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SECEnergyPriceSensor(coordinator, entry),
        SECEnergyForecastSensor(coordinator, entry),
        SECEnergyBasePriceSensor(coordinator, entry),
    ])


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
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        return get_current_price(tariff, datetime.now())

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
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        return get_current_price(tariff, datetime.now())

    @property
    def extra_state_attributes(self):
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return {}
        
        now = datetime.now()
        forecast = []
        for i in range(25):
            future = now + timedelta(hours=i)
            future_hour = future.replace(minute=0, second=0, microsecond=0)
            if future_hour < now.replace(minute=0, second=0, microsecond=0):
                future_hour += timedelta(hours=1)
            forecast.append({
                "hour": future_hour.isoformat(),
                "price": get_current_price(tariff, future_hour),
                "price_unit": "CHF/kWh"
            })
        
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
        tariff = self.coordinator.data.get("tariff")
        if not tariff:
            return None
        prices = tariff.get("prices", {})
        base = prices.get("base", {})
        return base.get("price", 0)


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
        return energy_tiers[-1]["price"]
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
