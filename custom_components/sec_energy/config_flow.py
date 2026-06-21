import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

# Vordefinierte DSOs (Stromversorger) mit ihren API-URLs
PREDEFINED_DSOS = {
    "Stadtwerke Wetzikon": "https://sec-energy.ch/tarifdaten/wetzikon/Tarifdaten_2026_Stadtwerke_Wetzikon.json",
    "Custom / Other": "custom",
}

class SECEnergyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("tariff", default=self.config_entry.data.get("tariff", "S-Standard")): str,
                vol.Optional("scan_interval", default=self.config_entry.data.get("scan_interval", 300)): int,
            })
        )

@config_entries.HANDLERS.register(DOMAIN)
class SECEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SECEnergyOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Erster Schritt: DSO (Stromversorger) auswählen"""
        errors = {}
        
        if user_input is not None:
            dso_selection = user_input.get("dso")
            
            if dso_selection == "Custom / Other":
                # Benutzer will eigene URL eingeben
                return await self.async_step_custom_url()
            
            # Vordefinierter DSO
            self.context["dso_name"] = dso_selection
            self.context["dso_url"] = PREDEFINED_DSOS[dso_selection]
            return await self.async_step_tariff()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("dso", default="Stadtwerke Wetzikon"): vol.In(list(PREDEFINED_DSOS.keys())),
            }),
            errors=errors,
            description_placeholders={
                "info": "Wähle deinen Stromversorger aus der Liste."
            }
        )

    async def async_step_custom_url(self, user_input=None):
        """Benutzer gibt eigene API-URL ein"""
        errors = {}
        
        if user_input is not None:
            url = user_input.get("custom_url", "").strip()
            if not url:
                errors["custom_url"] = "required"
            elif not url.startswith("http"):
                errors["custom_url"] = "invalid_url"
            else:
                try:
                    # Teste die URL
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            data = await response.json()
                            if "tariffs" not in data:
                                errors["base"] = "invalid_format"
                            else:
                                self.context["dso_name"] = data.get("dsoName", "Custom DSO")
                                self.context["dso_url"] = url
                                return await self.async_step_tariff()
                except Exception:
                    errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="custom_url",
            data_schema=vol.Schema({
                vol.Required("custom_url", default=""): str,
            }),
            errors=errors,
            description_placeholders={
                "info": "Gib die URL zu den Tarifdaten im SEC-Energy-Format ein."
            }
        )

    async def async_step_tariff(self, user_input=None):
        """Tarif auswählen - dynamisch aus der API geladen"""
        errors = {}
        
        dso_url = self.context.get("dso_url")
        dso_name = self.context.get("dso_name", "SEC Energy")
        
        if user_input is not None:
            # Tarif wurde gewählt, erstelle den Eintrag
            return self.async_create_entry(
                title=user_input.get("name", dso_name),
                data={
                    "name": user_input.get("name", dso_name),
                    "dso_url": dso_url,
                    "dso_name": dso_name,
                    "tariff": user_input["tariff"],
                    "scan_interval": user_input.get("scan_interval", 300),
                }
            )
        
        # Lade Tarife von der API
        tariff_choices = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(dso_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    data = await response.json()
                    
            for t in data.get("tariffs", []):
                name = t.get("tariffName", "Unknown")
                t_type = t.get("tariffType", "")
                t_form = t.get("tariffForm", "")
                # Zeige Typ und Form im Namen an
                label = f"{name} ({t_type}, {t_form})"
                tariff_choices[name] = label
                
        except Exception:
            errors["base"] = "cannot_connect"
            # Fallback: leere Liste
            tariff_choices = {}
        
        if not tariff_choices:
            errors["base"] = "no_tariffs"
        
        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema({
                vol.Required("name", default=dso_name): str,
                vol.Required("tariff", default=list(tariff_choices.keys())[0] if tariff_choices else ""): vol.In(tariff_choices),
                vol.Optional("scan_interval", default=300): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
            }),
            errors=errors,
            description_placeholders={
                "dso": dso_name,
                "info": f"Wähle deinen Tarif bei {dso_name}."
            }
        )
