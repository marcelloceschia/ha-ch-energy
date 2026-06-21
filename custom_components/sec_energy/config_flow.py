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
    "ACA Airolo": "https://www.comuneairolo.ch/azienda-elettrica/pdfDownloadHome/air_elettrica_1_9.json",
    "AEW": "https://aew.ch/sites/default/files/20260129_tariffs.json",
    "Arbon Energie AG": "https://sec-energy.ch/tarifdaten/arbon/Tarifdaten_2026_Arbon_Energie_AG.json",
    "Commune de Paudex": "https://www.paudex.ch/static/tarif-electricite.json",
    "Comune di Stabio, Elettrica": "https://amstabio.ch/fileadmin/user_upload/tariffe_2026.json",
    "EGH Elektro-Genossenschaft Hünenberg": "https://egh.ch/wp-content/uploads/2025/08/Tarife_2026_20250811_tariffs.json",
    "EGO Elektrizitätsgenossenschaft Otelfingen": "https://www.eg-otelfingen.ch/downloads/EGO_20250822_tarife.json",
    "EV Gebenstorf AG": "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250828_evgebenstorf_strompreise_2026.json",
    "EW Lachen AG": "https://www.ewlachen.ch/images/PDF/Strom/Strompreise2026/tarife-ew-lachen-2026.json",
    "EW Rothrist AG": "http://www.ewrothrist.ch/wAssets/docs/downloads/Preise-Energie-Netzprodukte/Preise-2026/20250826_tariffs.json",
    "EW Sirnach AG": "https://ewsirnach.ch/userdata/download/Strompreise/2026/preise-2026-ewsirnach-maschinenlesbar.json",
    "EW Uznach": "https://ewu.ch/wp-content/uploads/2025/08/Tarife_EW_Uznach_2026-1.json",
    "EWK Energie AG": "https://ewk-energie.ch/wp-content/uploads/2025/08/Tarife_EWK-Energie-AG_2026.json",
    "EWL Genossenschaft": "https://www.ewl.ch/media/filer/2025/20250828_tariffs.json",
    "Elektra Aristau (VNB)": "https://www.elektra-aristau.ch/media/tarifs_json/Tarife_ElektraAristau_2026.json",
    "Elektra Beinwil": "https://www.elektra-beinwil.ch/sites/default/files/Tarife_Elektra_Beinwil_2026.json",
    "Elektra Büttikon": "https://www.buettikon.ch/sites/default/files/2025-08/Tarife_Elektra-Bu%CC%88ttikon_2026.json",
    "Elektra Genossenschaft Arni-Islisberg": "https://egai.ch/index_htm_files/Tarife_Elektra_Arni-Islisberg_2026.json",
    "Elektra Hermetschwil-Staffeln": "https://www.elektra-hermetschwil.ch/sites/default/files/Tarife_Elektra_Hermetschwil-Staffeln_2026.json",
    "Elektra Horn AG": "https://sec-energy.ch/tarifdaten/horn/Tarifdaten_2026_Elektra_Horn_AG.json",
    "Elektra Mettauertal und Umgebung": "https://www.emu-hottwil.ch/_docn/166696/20250827_tariffs.json",
    "Elektra Remetschwil": "https://elektra-remetschwil.ch/view/data/9595/Tarife_Elektra_Remetschwil_2026.json",
    "Elektra Rüthi (SG)": "https://ruethi.ch/wp-content/uploads/2023/11/Tarife-Ruethi-2026.json",
    "Elektra Sins": "https://www.elektra-sins.ch/wp-content/uploads/2025/08/Tarife_Elektra_Sins_2026.json",
    "Elektra Sissach": "https://www.elektra-sissach.ch/fileadmin/user_upload/Elektra/maschinenlesbare_Tarife/Tarife_Elektra-Sissach_2026.json",
    "Elektra-Genossenschaft Siglistorf-Siglistorf-Wislikofen": "http://www.egswm.ch/userfiles/file/20250804_tariffs.json",
    "Elektra-Korporation Wolfhalden EKW": "https://ekw.ch/wp-content/uploads/2025/08/20250831_EKw_-Tarife_-2026.json",
    "Elektrizität Wasser Neuenhof": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Neuenhof_tariffs_2026.json",
    "Elektrizitäts- und Wasserwerk Windisch": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Windisch_tariffs_2026.json",
    "Elektrizitäts-Genossenschaft Brüschwil-Sonnenberg": "https://www.hefenhofen.ch/fileadmin/hefenhofen/EBS_Tarifblatt_2026_final_maschinenlesbar_Form.json",
    "Elektrizitäts-Genossenschaft Merenschwand": "https://elektra-merenschwand.ch/wp-content/uploads/2025/08/Tarife_Elektrizit%C3%A4ts-Genossenschaft_Merenschwand_2026.json",
    "Elektrizitätsgenossenschaft Jonen": "https://downloads.elektra-jonen.ch/Tarife_Elektrizitaetsgenossenschaft-Jonen_2026.json",
    "Elektrizitätsgenossenschaft Mühlau (VNB)": "https://www.elektra-muehlau.ch/assets/downloads/strom/2026/tarife_elektrizitaetsgenossenschaft-muehlau-_vnb__2026.json",
    "Elektrizitätsgenossenschaft Mülligen": "https://egm-strom.ch/wp-content/uploads/2025/08/Tarife_ElektrizitaetsgenossenschaftMuelligen_2026.json",
    "Elektrizitätsversorgung Kaisten": "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250828_evkaisten_strompreise_2026.json",
    "Elektrizitätsversorgung Killwangen": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Killwangen_tariffs_2026.json",
    "Elektrizitätsversorgung Mellingen": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Mellingen_tariffs_2026.json",
    "Elektrizitätsversorgung Mörschwil": "https://www.moerschwil.ch/_docn/6072058/moerschwil_tariffs_2026.json",
    "Elektrizitätsversorgung Villigen (EVV)": "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250827_evvilligen_strompreise_2026.json",
    "Elektrizitätsversorgung Zeihen (EVZ)": "https://energieverbrauch.ch/download/Tarife/Tarife_Elektrizit%C3%A4tsversorgung-Zeihen_2026.json",
    "Elektrizitätswerk Jona-Rapperswil AG": "https://ewjr.ch/images/json/20250825_tariffs_EWJR.json",
    "Elektrizitätswerk Muhen": "https://www.muhen.ch/public/upload/assets/3522/Tarife_Elektrizit%C3%A4tswerk-Muhen_2026.json",
    "Elektrizitätswerk Rümlang Genossenschaft": "https://www.ewruemlang.ch/uploads/files/Dokumente/ELCOM_Upload/2026-Maschinenlesbare-EWR-Tarife.json",
    "Elektrizitätswerk Sennwald": "https://www.ewsennwald.ch/fileadmin/user_upload/EW_Sennwald_Tarife_2026.json",
    "Energie Gossau AG": "https://energiegossau.ch/site/assets/files/1029/tarife_energie_gossau_ag_2026.json",
    "Energie Grüningen AG": "https://energie-grueningen.ch/neu/wp-content/uploads/2025/08/Tarife_Energie_Grueningen_AG_2026.json",
    "Energie Kreuzlingen": "https://energiekreuzlingen.ch/maschinenlesbar_mitteilung_tarifaenderungen_2026_energie_kreuzlingen.json",
    "Energie Münchenbuchsee AG": "https://www.energiebuchsi.ch/de/angebot/strom/20250811-tariffs.json",
    "Energie Thun AG": "https://energiethun.ch/app/uploads/2025/08/Tarife-Energie-Thun-AG-2026.json",
    "Energie Wettingen AG": "https://www.energiewettingen.ch/api/rm/82F24B75YCP3U59/20250814-enw-2026-tariffs.json",
    "Eniwa AG": "https://cms.eniwa.ch/assets/files/Downloads/Sonstiges/2026_Eniwa_tariffs.json",
    "Gemeinde Würenlingen Technische Werke": "https://www.wuerenlingen.ch/fileadmin/Tarife_Gemeinde_Wuerenlingen_Technische_Werke_2026.json",
    "Gemeindewerke Erstfeld": "https://www.gemeindewerke-erstfeld.ch/wp-content/uploads/2025/08/2026-Stromtarife-GWE-MRD.json",
    "Gemeindewerke Pfäffikon ZH": "https://baldium.digital/gwp/20250826_tariffs.json",
    "Genossenschaft EW Münchwilen": "https://ewmuenchwilen.ch/userdata/dateien/Strompreise%202026/preise-2026-ewmuenchwilen-maschinenlesbar.json",
    "Genossenschaft Elektra Busslingen": "https://www.elektra-busslingen.ch/downloads/2026_tarife__elektra_busslingen.json",
    "Genossenschaft Elektra Egnach": "https://energie-egnach.ch/wp-content/uploads/egnach_tariffs_2026.json",
    "Genossenschaft Elektra Ehrendingen": "https://2883444f-3a65-4331-9f4e-391db333c6a8.filesusr.com/ugd/632990_7710b4991ee040afb14e2b6f26360cdc.json?dn=Elektra_Ehrendingen_tariffs.json",
    "Genossenschaft Elektra Fislisbach": "https://1f4470fa-78e1-4b23-a611-1bbbfe3ab455.filesusr.com/ugd/8d6ae8_9007be0427994751b173724ea32abfdc.json?dn=Tarife_Genossenschaft_Elektra%20Fislisbach_2026.json",
    "Genossenschaft Elektra, Jegenstorf": "https://www.elektra.ch/wp-content/uploads/2025/09/20250926_tariffs.json",
    "Genossenschaft Elektrizitäts- und Wasserwerk Dozwil": "https://www.dozwil.ch/documents/werke/tarife_genossenschaftelektrizitaetsundwasserwerkdozwil_2026.json",
    "Genossenschaft Energie Fischingen": "https://energie-fischingen.ch/wp-content/uploads/Tarife_EnergieFischingen_2026.json",
    "Groupe E": "https://www.groupe-e.ch/tarifs/tarifs.json",
    "IB Wohlen AG": "https://www.ibw.ag/mm/Tarife_IB_Wohlen_AG_2026.json",
    "IBB Strom AG": "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250917_ibb_strompreise_2026.json",
    "IWB": "https://www.iwb.ch/dam/jcr:4c273699-fbe7-4e2e-bdb4-cf908631dd1c/maschinell-lesbare-tarife-strom.json",
    "Industrielle Betriebe Interlaken AG": "https://www.ibi.ch/download/documents/2e/f3c23qsicm3k9idz2arnv0qoxxew05/20250825_tariffs.json",
    "Infrastruktur Zürichsee AG": "https://www.infra-z.ch/images/downloads/Tarife_Strom_maschinenlesbares_Format_2026.json",
    "Localnet AG": "https://www.localnet.ch/fileadmin/user_upload/Strom/Formulare_und_PDF/Maschinenlesbare_Information.json",
    "OIKEN SA": "https://oiken.ch/tarifs/tariffs_OIKEN_2026.json",
    "RTB": "https://rtb-wildegg.ch/media/files/20250827_tariffs.json",
    "Regio Energie Amriswil (REA)": "https://rea.swiss/wp-content/uploads/Tarifblatt-Strom-REA-2026-maschinenlesbar.json",
    "Regionalwerke AG Baden": "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Baden_tariffs_2026.json",
    "Romande Energie": "https://corpweb-st-prd-chn-dcdedafvgsbuejdj.a01.azurefd.net/public/document/2025-08/tarifs_2026_RE.json",
    "SH POWER": "https://www.shpower.ch/fileadmin/stromtarife/shpower-stromtarife.json",
    "Sinergy Infrastructure SA": "https://www.sinergy.ch/files/20250827_tariffs.json",
    "Société Electrique de la Vallée de Joux SA": "https://www.sevj.ch/wp-content/uploads/2025/08/20250825_tariffs-1.json",
    "St. Gallisch-Appenzellische Kraftwerke AG": "https://www.sak.ch/downloads/strom/strompreise/sak-tarife-2026.json",
    "Stadtwerke Wetzikon": "https://sec-energy.ch/tarifdaten/wetzikon/Tarifdaten_2026_Stadtwerke_Wetzikon.json",
    "Technische Betriebe Birmenstorf": "https://energieverbrauch.ch/download/Tarife/Technische_Betriebe_Birmenstorf_2026.json",
    "Technische Betriebe Glarus Nord (TBGN)": "https://www.tbgn.ch/images/T2026/TBGN-Strom-Tarife-2026.json",
    "Technische Betriebe Oberentfelden": "https://www.oberentfelden.ch/sites/default/files/2025-08/Tarife_Technische_Betriebe_Oberentfelden_2026.json",
    "Technische Betriebe Weinfelden AG": "https://tbweinfelden.ch/stromtarife/stromtarife-2026.json",
    "Technische Gemeindebetriebe Wängi": "https://tbwaengi.ch/userdata/files/preise_2026_tbwaengi_maschinenlesbar.json",
    "Technische Werke Eschlikon": "https://www.eschlikon.ch/public/upload/assets/5485/preise-2026-tweschlikon_maschinenlesbar.json",
    "Thurwerke AG": "https://thurwerke.ch/wp-content/uploads/2025/08/Tarifblatt_2026_Thurwerke_AG.json",
    "Viteos SA": "https://www.viteos.ch/wp-content/tarifs/tarifs_electriques_2026.json",
    "Werke Horgen": "https://sec-energy.ch/tarifdaten/horgen/Tarifdaten_2026_Werke_Horgen.json",
    "Werke Wangen-Brüttisellen": "https://www.werkewb.ch/tarife-elcom/WWB_20250830_tariffs.json",
    "Werke am Zürichsee AG (Erlenbach)": "https://werkezuerichsee.ch/wp-content/uploads/2026_erlenbach.json",
    "Werke am Zürichsee AG (Küsnacht)": "https://werkezuerichsee.ch/wp-content/uploads/2026_kuesnacht.json",
    "Werke am Zürichsee AG (Zollikon)": "https://werkezuerichsee.ch/wp-content/uploads/2026_zollikon.json",
    "eug Elektra Untergäu Genossenschaft": "https://www.eug.ch/media/ziwps1q4/20250807_tariffs_final.json",
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
