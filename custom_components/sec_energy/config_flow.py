import logging
import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Vordefinierte DSOs (Stromversorger) mit ihren API-URLs
# Generiert aus SEC-Energy API (Stand: 2026-06-21, 93 Anbieter)
PREDEFINED_DSOS = {
    "AEW": "https://aew.ch/sites/default/files/20260129_tariffs.json",
    "Arbon Energie AG": "https://sec-energy.ch/tarifdaten/arbon/Tarifdaten_2026_Arbon_Energie_AG.json",
    "ACA Airolo": "https://www.comuneairolo.ch/azienda-elettrica/pdfDownloadHome/air_elettrica_1_9.json",
    "SH POWER": "https://www.shpower.ch/fileadmin/stromtarife/shpower-stromtarife.json",
    "Commune de Paudex": "https://www.paudex.ch/static/tarif-electricite.json",
    "Comune di Stabio, Elettrica": "https://amstabio.ch/fileadmin/user_upload/tariffe_2026.json",
    "EGH Elektro-Genossenschaft Hünenberg": "https://egh.ch/wp-content/uploads/2025/08/Tarife_2026_20250811_tariffs.json",
    "Technische Betriebe Birmenstorf": "https://energieverbrauch.ch/download/Tarife/Technische_Betriebe_Birmenstorf_2026.json",
    "Elektrizitätswerk Muhen": "https://www.muhen.ch/public/upload/assets/3522/Tarife_Elektrizit%C3%A4tswerk-Muhen_2026.json",
    "Elektrizitätsversorgung Villigen (EVV)": "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250827_evvilligen_strompreise_2026.json",
    "Elektrizitäts- und Wasserwerk Windisch": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Windisch_tariffs_2026.json",
    "Elektrizitätsversorgung Zeihen (EVZ)": "https://energieverbrauch.ch/download/Tarife/Tarife_Elektrizit%C3%A4tsversorgung-Zeihen_2026.json",
    "Elektra Genossenschaft Arni-Islisberg": "https://egai.ch/index_htm_files/Tarife_Elektra_Arni-Islisberg_2026.json",
    "Elektra Horn AG": "https://sec-energy.ch/tarifdaten/horn/Tarifdaten_2026_Elektra_Horn_AG.json",
    "Elektra-Korporation Wolfhalden EKW": "https://ekw.ch/wp-content/uploads/2025/08/20250831_EKw_-Tarife_-2026.json",
    "Elektra Mettauertal und Umgebung": "https://www.emu-hottwil.ch/_docn/166696/20250827_tariffs.json",
    "Elektra Remetschwil": "https://elektra-remetschwil.ch/view/data/9595/Tarife_Elektra_Remetschwil_2026.json",
    "Elektrizitätsgenossenschaft Mellingen (EGM)": "https://egm-strom.ch/wp-content/uploads/2025/08/Tarife_ElektrizitaetsgenossenschaftMuelligen_2026.json",
    "Elektrizitäts-Genossenschaft Merenschwand": "https://elektra-merenschwand.ch/wp-content/uploads/2025/08/Tarife_Elektrizit%C3%A4ts-Genossenschaft_Merenschwand_2026.json",
    "Elektra Aristau": "https://www.elektra-aristau.ch/media/tarifs_json/Tarife_ElektraAristau_2026.json",
    "Elektra Beinwil": "https://www.elektra-beinwil.ch/sites/default/files/Tarife_Elektra_Beinwil_2026.json",
    "Elektrizitätswerk Hefenhofen": "https://www.hefenhofen.ch/fileadmin/hefenhofen/EBS_Tarifblatt_2026_final_maschinenlesbar_Form.json",
    "Elektra Hermetschwil": "https://www.elektra-hermetschwil.ch/sites/default/files/Tarife_Elektra_Hermetschwil-Staffeln_2026.json",
    "Elektrizitätsgenossenschaft Jonen": "https://downloads.elektra-jonen.ch/Tarife_Elektrizitaetsgenossenschaft-Jonen_2026.json",
    "Elektrizitätsgenossenschaft Mühlau": "https://www.elektra-muehlau.ch/assets/downloads/strom/2026/tarife_elektrizitaetsgenossenschaft-muehlau-_vnb__2026.json",
    "Elektrizitätsgenossenschaft Otelfingen (EGO)": "https://www.eg-otelfingen.ch/downloads/EGO_20250822_tarife.json",
    "Elektrizitätsgenossenschaft Rümikon": "https://egruemikon.ch/contentpics/File/Tarife_Elektrizitaetsgenossenschaft_Ruemikon_2026.json",
    "Elektra Oberrohrdorf (EOR)": "https://www.eor.ch/wp-content/uploads/2025/08/Tarife_Elektra_Oberrohrdorf_VNB_2026.json",
    "IB Wohlen AG": "https://www.ibw.ag/mm/Tarife_IB_Wohlen_AG_2026.json",
    "Stadtwerke Schaffhausen (SGSW)": "https://www.sgsw.ch/home/strom/tarife/_jcr_content/Par/sgsw_accordion_list_/AccordionListPar/sgsw_accordion_12353_1221402959/AccordionPar/sgsw_downloadlist/DownloadListPar/sgsw_download.ocFile/2026%20Strompreise%20maschinenlesbar.json",
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
                    import json
                    async with aiohttp.ClientSession(headers={"User-Agent": "HomeAssistant-SEC-Energy/1.0"}) as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            text = await response.text()
                            data = json.loads(text)
                            if "tariffs" not in data:
                                errors["base"] = "invalid_format"
                            else:
                                self.context["dso_name"] = data.get("dsoName", "Custom DSO")
                                self.context["dso_url"] = url
                                return await self.async_step_tariff()
                except json.JSONDecodeError:
                    _LOGGER.error("Ungültiges JSON von Custom URL")
                    errors["base"] = "invalid_format"
                except aiohttp.ClientError as err:
                    _LOGGER.error("HTTP Fehler bei Custom URL: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    _LOGGER.error("Unerwarteter Fehler bei Custom URL: %s", err, exc_info=True)
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
        
        _LOGGER.debug("async_step_tariff aufgerufen: dso_url=%s, dso_name=%s", dso_url, dso_name)
        
        if user_input is not None:
            _LOGGER.debug("Tarif gewählt: %s", user_input)
            # Tarif wurde gewählt, erstelle den Eintrag
            return self.async_create_entry(
                title=user_input.get("name", dso_name),
                data={
                    "name": user_input.get("name", dso_name),
                    "dso_url": dso_url,
                    "dso_name": dso_name,
                    "tariff": user_input["tariff"],
                    "scan_interval": user_input.get("scan_interval", 86400),
                }
            )
        
        # Lade Tarife von der API
        tariff_choices = {}
        text = None
        try:
            import json
            _LOGGER.debug("Lade Tarife von URL: %s", dso_url)
            async with aiohttp.ClientSession(headers={"User-Agent": "HomeAssistant-SEC-Energy/1.0"}) as session:
                async with session.get(dso_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    _LOGGER.debug("HTTP Status: %s, Content-Type: %s", response.status, response.headers.get('content-type'))
                    text = await response.text()
                    _LOGGER.debug("Response Länge: %d chars", len(text))
                    _LOGGER.debug("Response Preview (first 500 chars): %s", text[:500])
                    data = json.loads(text)
                    _LOGGER.debug("JSON geparst. Keys: %s", list(data.keys()))
                    _LOGGER.debug("Anzahl Tarife: %d", len(data.get("tariffs", [])))
                    
            for t in data.get("tariffs", []):
                name = t.get("tariffName", "Unknown")
                t_type = t.get("tariffType", "")
                t_form = t.get("tariffForm", "")
                # Zeige Typ und Form im Namen an
                label = f"{name} ({t_type}, {t_form})"
                tariff_choices[name] = label
                _LOGGER.debug("Tarif gefunden: %s -> %s", name, label)
                
        except json.JSONDecodeError as err:
            _LOGGER.error("JSON Decode Fehler: %s", err)
            _LOGGER.error("Text preview: %s", text[:200] if text else "N/A")
            errors["base"] = "cannot_connect"
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP Client Fehler: %s", err)
            errors["base"] = "cannot_connect"
        except Exception as err:
            _LOGGER.error("Unerwarteter Tarif-Ladefehler: %s", err, exc_info=True)
            errors["base"] = "cannot_connect"
            # Fallback: leere Liste
            tariff_choices = {}
        
        if not tariff_choices:
            _LOGGER.warning("Keine Tarife gefunden für URL: %s", dso_url)
            errors["base"] = "no_tariffs"
        
        _LOGGER.debug("Tarif-Formular wird angezeigt. %d Tarife verfügbar. Fehler: %s", len(tariff_choices), errors)
        
        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema({
                vol.Required("name", default=dso_name): str,
                vol.Required("tariff", default=list(tariff_choices.keys())[0] if tariff_choices else ""): vol.In(tariff_choices),
                vol.Optional("scan_interval", default=86400): vol.All(vol.Coerce(int), vol.Range(min=60, max=604800)),
            }),
            errors=errors,
            description_placeholders={
                "dso": dso_name,
                "info": f"Wähle deinen Tarif bei {dso_name}."
            }
        )
