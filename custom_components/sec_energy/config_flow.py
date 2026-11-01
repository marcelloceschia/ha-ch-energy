import logging
import voluptuous as vol
import aiohttp
import json
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN
from .tariffs import resolve_document, covers, select_tariff
from homeassistant.util import dt as dt_util


async def fetch_document(url):
    """Fetch JSON with status checks; normalize transport errors for fallback."""
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "HomeAssistant-SEC-Energy/1.0"}) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise OSError(f"HTTP {response.status}")
                return json.loads(await response.text())
    except aiohttp.ClientError as err:
        raise OSError(str(err)) from err


_LOGGER = logging.getLogger(__name__)

# SEC Energy JSON Schema (inline für Home Assistant)
SEC_ENERGY_SCHEMA = {
    "required": ["dsoName", "dsoNumber", "tariffs"],
    "properties": {
        "dsoName": {"type": "string"},
        # Official schema uses integer; some DSOs publish the 11-digit ID as text.
        "dsoNumber": {"anyOf": [
            {"type": "integer"},
            {"type": "string", "pattern": "^[0-9]{11}$", "maxLength": 11},
        ]},
        "tariffs": {
            "type": "array",
            "minItems": 1,
            "items": {
                "required": ["tariffName", "tariffType", "tariffForm", "prices"],
                "properties": {
                    "tariffName": {"type": "string"},
                    "tariffType": {"type": "string", "enum": ["grid", "electricity", "metering", "other"]},
                    "tariffForm": {"type": "string", "enum": ["multilevel", "constant", "other"]},
                    "prices": {
                        "required": ["base", "energy"],
                        "properties": {
                            "base": {
                                "required": ["price", "priceUnit"],
                                "properties": {
                                    "price": {"type": "number"},
                                    "priceUnit": {"type": "string"}
                                }
                            },
                            "energy": {
                                "type": "array",
                                "items": {
                                    "required": ["months", "weekdays", "from", "to", "price", "priceUnit"],
                                    "properties": {
                                        "months": {"type": "array", "items": {"type": "string"}},
                                        "weekdays": {"type": "array", "items": {"type": "string"}},
                                        "from": {"type": "string", "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$"},
                                        "to": {"type": "string", "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$"},
                                        "price": {"type": "number", "minimum": 0},
                                        "priceUnit": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

def validate_schema(data):
    """Validiere SEC-Energy JSON Schema"""
    errors = []
    
    # Root level
    for field in SEC_ENERGY_SCHEMA["required"]:
        if field not in data:
            errors.append(f"Fehlendes Pflichtfeld: {field}")
    
    if not isinstance(data.get("dsoName"), str):
        errors.append("dsoName muss ein String sein")
    
    dso_number = data.get("dsoNumber")
    # Do not coerce arbitrary values or accept bool (a Python int subclass).
    if not (
        type(dso_number) is int
        or (
            isinstance(dso_number, str)
            and len(dso_number) == 11
            and dso_number.isascii()
            and dso_number.isdecimal()
        )
    ):
        errors.append("dsoNumber muss eine Ganzzahl oder ein String aus 11 ASCII-Ziffern sein")
    
    tariffs = data.get("tariffs", [])
    if not isinstance(tariffs, list) or len(tariffs) == 0:
        errors.append("tariffs muss ein Array mit mindestens 1 Element sein")
    else:
        for i, tariff in enumerate(tariffs):
            for field in ["tariffName", "tariffType", "tariffForm", "prices"]:
                if field not in tariff:
                    errors.append(f"Tarif {i}: Fehlendes Feld '{field}'")
            
            tariff_type = tariff.get("tariffType")
            prices = tariff.get("prices", {})
            if not isinstance(prices, dict):
                errors.append(f"Tarif {i}: prices muss ein Objekt sein")
            else:
                # Validierung je nach tariffType
                if tariff_type in ("electricity", "grid"):
                    if "energy" not in prices:
                        errors.append(f"Tarif {i}: prices.energy fehlt für Typ '{tariff_type}'")
                    elif not isinstance(prices.get("energy"), list):
                        errors.append(f"Tarif {i}: prices.energy muss ein Array sein")
                elif tariff_type == "metering":
                    if "base" not in prices:
                        errors.append(f"Tarif {i}: prices.base fehlt für Typ 'metering'")
                elif tariff_type == "regional_fees":
                    if "municipalityTaxes" not in prices:
                        errors.append(f"Tarif {i}: prices.municipalityTaxes fehlt für Typ 'regional_fees'")
                # Für andere Typen keine strikte Validierung der prices-Felder
    
    return errors

# Vordefinierte DSOs: Jahres-Map {int: URL}; nur jahreslose Quellen als String.
# Publikations-Datestamps sind keine Tarifjahre: bestehende URLs bleiben unter 2026.
# Generiert aus SEC-Energy API (Stand: 2026-06-21, 93 Anbieter)
PREDEFINED_DSOS = {
    "ACA Airolo": "https://www.comuneairolo.ch/azienda-elettrica/pdfDownloadHome/air_elettrica_1_9.json",
    "AEW": {2026: "https://aew.ch/sites/default/files/20260129_tariffs.json"},
    "Arbon Energie AG": {2026: "https://sec-energy.ch/tarifdaten/arbon/Tarifdaten_2026_Arbon_Energie_AG.json", 2027: "https://sec-energy.ch/tarifdaten/arbon/tariffs-10047012345-arbon-energie-ag-2027.json"},
    "Commune de Paudex": "https://www.paudex.ch/static/tarif-electricite.json",
    "Comune di Stabio, Elettrica": {2026: "https://amstabio.ch/fileadmin/user_upload/tariffe_2026.json", 2027: "https://www.amstabio.ch/fileadmin/user_upload/documenti/elettricita/tariffe_2027.json"},
    "EGH Elektro-Genossenschaft Hünenberg": {2026: "https://egh.ch/wp-content/uploads/2025/08/Tarife_2026_20250811_tariffs.json", 2027: "https://egh.ch/wp-content/uploads/2026/08/Tarife_2026-2027_20260819_tariffs.json"},
    "EGO Elektrizitätsgenossenschaft Otelfingen": {2026: "https://www.eg-otelfingen.ch/downloads/EGO_20250822_tarife.json", 2027: "https://www.eg-otelfingen.ch/downloads/EGO_Tarife_2027_20260825_tariffs.json"},
    "EV Gebenstorf AG": {2026: "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250828_evgebenstorf_strompreise_2026.json", 2027: "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2027/20260825_evgebenstorf_strompreise_2027.json"},
    "EW Lachen AG": {2026: "https://www.ewlachen.ch/images/PDF/Strom/Strompreise2026/tarife-ew-lachen-2026.json", 2027: "https://www.ewlachen.ch/images/PDF/Strom/Strompreise_2027/tarife-ew-lachen-2027.json"},
    "EW Rothrist AG": {2026: "http://www.ewrothrist.ch/wAssets/docs/downloads/Preise-Energie-Netzprodukte/Preise-2026/20250826_tariffs.json", 2027: "http://www.ewrothrist.ch/wAssets/docs/downloads/Preise-Energie-Netzprodukte/Preise-2027/20260827_tariffs.json"},
    "EW Sirnach AG": {2026: "https://ewsirnach.ch/userdata/download/Strompreise/2026/preise-2026-ewsirnach-maschinenlesbar.json", 2027: "https://ewsirnach.ch/userdata/download/Strompreise/2027/preise-2027-ewsirnach-maschinenlesbar.json"},
    "EW Uznach": {2026: "https://ewu.ch/wp-content/uploads/2025/08/Tarife_EW_Uznach_2026-1.json"},
    "EWK Energie AG": {2026: "https://ewk-energie.ch/wp-content/uploads/2025/08/Tarife_EWK-Energie-AG_2026.json"},
    "EWL Genossenschaft": {2026: "https://www.ewl.ch/media/filer/2025/20250828_tariffs.json", 2027: "https://www.ewl.ch/media/filer/2026/20260831_tariffs.json"},
    "Elektra Aristau (VNB)": {2026: "https://www.elektra-aristau.ch/media/tarifs_json/Tarife_ElektraAristau_2026.json"},
    "Elektra Beinwil": {2026: "https://www.elektra-beinwil.ch/sites/default/files/Tarife_Elektra_Beinwil_2026.json"},
    "Elektra Büttikon": {2026: "https://www.buettikon.ch/sites/default/files/2025-08/Tarife_Elektra-Bu%CC%88ttikon_2026.json"},
    "Elektra Genossenschaft Arni-Islisberg": {2026: "https://egai.ch/index_htm_files/Tarife_Elektra_Arni-Islisberg_2026.json"},
    "Elektra Hermetschwil-Staffeln": {2026: "https://www.elektra-hermetschwil.ch/sites/default/files/Tarife_Elektra_Hermetschwil-Staffeln_2026.json"},
    "Elektra Horn AG": {2026: "https://sec-energy.ch/tarifdaten/horn/Tarifdaten_2026_Elektra_Horn_AG.json", 2027: "https://sec-energy.ch/tarifdaten/horn/tariffs-10839012345-elektra-horn-ag-2027.json"},
    "Elektra Mettauertal und Umgebung": {2026: "https://www.emu-hottwil.ch/_docn/166696/20250827_tariffs.json", 2027: "https://www.emu-hottwil.ch/_docn/181720/20260824_tariffs.json"},
    "Elektra Remetschwil": {2026: "https://elektra-remetschwil.ch/view/data/9595/Tarife_Elektra_Remetschwil_2026.json"},
    "Elektra Rüthi (SG)": {2026: "https://ruethi.ch/wp-content/uploads/2023/11/Tarife-Ruethi-2026.json", 2027: "https://ruethi.ch/wp-content/uploads/2026/08/Tarife-Ruethi-2026-2027.json"},
    "Elektra Sins": {2026: "https://strompreisvergleich.ch/tarife/data/10346012345/tarife.json", 2027: "https://strompreisvergleich.ch/tarife/data/10346012345/tarife.json"},
    "Elektra Sissach": {2026: "https://www.elektra-sissach.ch/fileadmin/user_upload/Elektra/maschinenlesbare_Tarife/Tarife_Elektra-Sissach_2026.json"},
    "Elektra-Genossenschaft Siglistorf-Siglistorf-Wislikofen": {2026: "http://www.egswm.ch/userfiles/file/20250804_tariffs.json", 2027: "https://www.egswm.ch/userfiles/file/Tarife_EGSWM_(VNB)_2026-2027.json"},
    "Elektra-Korporation Wolfhalden EKW": {2026: "https://ekw.ch/wp-content/uploads/2025/08/20250831_EKw_-Tarife_-2026.json", 2027: "https://ekw.ch/wp-content/uploads/2026/08/20260831_EKw-Tarife_2027.json"},
    "Elektrizität Wasser Neuenhof": {2026: "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Neuenhof_tariffs_2026.json", 2027: "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Neuenhof_tariffs.json"},
    "Elektrizitäts- und Wasserwerk Windisch": {2026: "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Windisch_tariffs_2026.json", 2027: "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Windisch_tariffs.json"},
    "Elektrizitäts-Genossenschaft Brüschwil-Sonnenberg": {2026: "https://www.hefenhofen.ch/fileadmin/hefenhofen/EBS_Tarifblatt_2026_final_maschinenlesbar_Form.json", 2027: "https://www.hefenhofen.ch/fileadmin/hefenhofen/EBS_Tarifblatt_2026_2027_final_maschinenlesbar_Form.json"},
    "Elektrizitäts-Genossenschaft Merenschwand": {2026: "https://elektra-merenschwand.ch/wp-content/uploads/2025/08/Tarife_Elektrizit%C3%A4ts-Genossenschaft_Merenschwand_2026.json"},
    "Elektrizitätsgenossenschaft Jonen": {2026: "https://downloads.elektra-jonen.ch/Tarife_Elektrizitaetsgenossenschaft-Jonen_2026.json"},
    "Elektrizitätsgenossenschaft Mühlau (VNB)": {2026: "https://www.elektra-muehlau.ch/assets/downloads/strom/2026/tarife_elektrizitaetsgenossenschaft-muehlau-_vnb__2026.json", 2027: "https://www.elektra-muehlau.ch/assets/downloads/strom/tarife_elektrizitaetsgenossenschaft_muehlau__vnb.json"},
    "Elektrizitätsgenossenschaft Mülligen": {2026: "https://egm-strom.ch/wp-content/uploads/2025/08/Tarife_ElektrizitaetsgenossenschaftMuelligen_2026.json"},
    "Elektrizitätsversorgung Kaisten": {2026: "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250828_evkaisten_strompreise_2026.json", 2027: "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2027/20260824_evkaisten_strompreise_2027.json"},
    "Elektrizitätsversorgung Killwangen": {2026: "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Killwangen_tariffs_2026.json", 2027: "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Killwangen_tariffs.json"},
    "Elektrizitätsversorgung Mellingen": {2026: "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Mellingen_tariffs_2026.json", 2027: "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Mellingen_tariffs.json"},
    "Elektrizitätsversorgung Mörschwil": {2026: "https://www.moerschwil.ch/_docn/6072058/moerschwil_tariffs_2026.json", 2027: "https://www.moerschwil.ch/_docn/7188874/Tarife_M%C3%B6rschwil_2027_%28maschinenlesbar%29.json"},
    "Elektrizitätsversorgung Villigen (EVV)": {2026: "https://25304444.fs1.hubspotusercontent-eu1.net/hubfs/25304444/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250827_evvilligen_strompreise_2026.json", 2027: "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2027/20260824_evvilligen_strompreise_2027.json"},
    "Elektrizitätsversorgung Zeihen (EVZ)": {2026: "https://energieverbrauch.ch/download/Tarife/Tarife_Elektrizit%C3%A4tsversorgung-Zeihen_2026.json"},
    "Elektrizitätswerk Jona-Rapperswil AG": {2026: "https://ewjr.ch/images/json/20250825_tariffs_EWJR.json"},
    "Elektrizitätswerk Muhen": {2026: "https://www.muhen.ch/public/upload/assets/3522/Tarife%20Elektrizit%C3%A4tswerk%20Muhen.json"},
    "Elektrizitätswerk Rümlang Genossenschaft": {2026: "https://www.ewruemlang.ch/uploads/files/Dokumente/ELCOM_Upload/2026-Maschinenlesbare-EWR-Tarife.json"},
    "Elektrizitätswerk Sennwald": {2026: "https://www.ewsennwald.ch/fileadmin/user_upload/EW_Sennwald_Tarife_2026.json"},
    "Energie Gossau AG": {2026: "https://strompreisvergleich.ch/tarife/data/10766012345/tarife.json", 2027: "https://strompreisvergleich.ch/tarife/data/10766012345/tarife.json"},
    "Energie Grüningen AG": {2026: "https://energie-grueningen.ch/neu/wp-content/uploads/2025/08/Tarife_Energie_Grueningen_AG_2026.json"},
    "Energie Kreuzlingen": {2026: "https://energiekreuzlingen.ch/maschinenlesbar_mitteilung_tarifaenderungen_2026_energie_kreuzlingen.json"},
    "Energie Münchenbuchsee AG": {2026: "https://www.energiebuchsi.ch/de/angebot/strom/20250811-tariffs.json", 2027: "https://www.energiebuchsi.ch/de/angebot/strom/20260824-tariffs-2027.json"},
    "Energie Thun AG": {2026: "https://energiethun.ch/app/uploads/2025/08/Tarife-Energie-Thun-AG-2026.json"},
    "Energie Wettingen AG": {2026: "https://www.energiewettingen.ch/upload/rm/20/26/20260824-enw-2027-tariffs-1.json", 2027: "https://www.energiewettingen.ch/upload/rm/20/26/20260824-enw-2027-tariffs-1.json"},
    "Eniwa AG": {2026: "https://cms.eniwa.ch/assets/files/Downloads/Sonstiges/2026_Eniwa_tariffs.json", 2027: "https://cms.eniwa.ch/assets/files/Downloads/Sonstiges/eniwa_maschinenlesbare_stromtarife_2026_2027.json"},
    "Gemeinde Würenlingen Technische Werke": {2026: "https://www.wuerenlingen.ch/fileadmin/Tarife_Gemeinde_Wuerenlingen_Technische_Werke_2026.json"},
    "Gemeindewerke Erstfeld": {2026: "https://www.gemeindewerke-erstfeld.ch/wp-content/uploads/2025/08/2026-Stromtarife-GWE-MRD.json", 2027: "https://www.gemeindewerke-erstfeld.ch/wp-content/uploads/2026/08/Tarifsammlung-Gemeindewerke-Erstfeld.json"},
    "Gemeindewerke Pfäffikon ZH": {2026: "https://baldium.digital/gwp/20250826_tariffs.json"},
    "Genossenschaft EW Münchwilen": {2026: "https://ewmuenchwilen.ch/userdata/dateien/Strompreise%202026/preise-2026-ewmuenchwilen-maschinenlesbar.json", 2027: "https://ewmuenchwilen.ch/userdata/dateien/Strompreise%202027/tariffs-10275012345-genossenschaft-ew-m-nchwilen.json"},
    "Genossenschaft Elektra Busslingen": {2026: "https://www.elektra-busslingen.ch/downloads/2026_tarife__elektra_busslingen.json"},
    "Genossenschaft Elektra Egnach": {2026: "https://energie-egnach.ch/wp-content/uploads/egnach_tariffs_2026.json", 2027: "https://energie-egnach.ch/wp-content/uploads/egnach_tariffs_2027.json"},
    "Genossenschaft Elektra Ehrendingen": "https://2883444f-3a65-4331-9f4e-391db333c6a8.filesusr.com/ugd/632990_7710b4991ee040afb14e2b6f26360cdc.json?dn=Elektra_Ehrendingen_tariffs.json",
    "Genossenschaft Elektra Fislisbach": {2026: "https://1f4470fa-78e1-4b23-a611-1bbbfe3ab455.filesusr.com/ugd/8d6ae8_9007be0427994751b173724ea32abfdc.json?dn=Tarife_Genossenschaft_Elektra%20Fislisbach_2026.json"},
    "Genossenschaft Elektra, Jegenstorf": {2026: "https://www.elektra.ch/wp-content/uploads/2025/09/20250926_tariffs.json", 2027: "https://www.elektra.ch/wp-content/uploads/2026/08/20260824_tariffs.json"},
    "Genossenschaft Elektrizitäts- und Wasserwerk Dozwil": {2026: "https://www.dozwil.ch/documents/werke/tarife_genossenschaftelektrizitaetsundwasserwerkdozwil_2026.json"},
    "Genossenschaft Energie Fischingen": {2026: "https://energie-fischingen.ch/wp-content/uploads/Tarife_EnergieFischingen_2026.json"},
    "Groupe E": "https://www.groupe-e.ch/tarifs/tarifs.json",
    "IB Wohlen AG": {2026: "https://www.ibw.ag/mm/Tarife_IB_Wohlen_AG_2026.json"},
    "IBB Strom AG": {2026: "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2026/20250917_ibb_strompreise_2026.json", 2027: "https://www.ibbrugg.ch/hubfs/IBB%20Webseite/Dokumente/Preisblaetter/2027/20260824_ibb_strompreise_2027.json"},
    "IWB": "https://www.iwb.ch/dam/jcr:4c273699-fbe7-4e2e-bdb4-cf908631dd1c/maschinell-lesbare-tarife-strom.json",
    "Industrielle Betriebe Interlaken AG": {2027: "https://www.ibi.ch/media/documents/20260821_tariffs.json"},
    "Infrastruktur Zürichsee AG": {2026: "https://www.infra-z.ch/images/downloads/Tarife_Strom_maschinenlesbares_Format_2026.json", 2027: "https://www.infra-z.ch/images/downloads/Tarife_Strom_maschinenlesbares_Format_2027.json"},
    "Localnet AG": "https://www.localnet.ch/fileadmin/user_upload/Strom/Formulare_und_PDF/Maschinenlesbare_Information.json",
    "OIKEN SA": {2026: "https://oiken.ch/tarifs/tariffs_OIKEN_2026.json", 2027: "https://oiken.ch/tarifs/Tarifs_OIKEN_2027.json"},
    "RTB": {2026: "https://rtb-wildegg.ch/media/files/20250827_tariffs.json", 2027: "https://www.rtb-wildegg.ch/media/files/20260826_tariffs.json"},
    "Regio Energie Amriswil (REA)": {2026: "https://rea.swiss/wp-content/uploads/Tarifblatt-Strom-REA-2026-maschinenlesbar.json", 2027: "https://rea.swiss/wp-content/uploads/Tarifblatt-Strom-REA-maschinenlesbar.json"},
    "Regionalwerke AG Baden": {2026: "https://www.regionalwerke.ch/fileadmin/Strompreise_ElCom/Baden_tariffs_2026.json", 2027: "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Baden_tariffs.json"},
    "Romande Energie": {2026: "https://corpweb-st-prd-chn-dcdedafvgsbuejdj.a01.azurefd.net/public/document/2025-08/tarifs_2026_RE.json", 2027: "https://corpweb-st-prd-chn-dcdedafvgsbuejdj.a01.azurefd.net/public/document/2026-08/20260821_tarifs%20RE_BVE%202027.json"},
    "SH POWER": "https://www.shpower.ch/fileadmin/stromtarife/shpower-stromtarife.json",
    "Sinergy Infrastructure SA": {2026: "https://www.sinergy.ch/files/20250827_tariffs.json", 2027: "https://www.sinergy.ch/files/20260818_tariffs.json"},
    "Société Electrique de la Vallée de Joux SA": {2026: "https://www.sevj.ch/wp-content/uploads/2025/08/20250825_tariffs-1.json"},
    "St. Gallisch-Appenzellische Kraftwerke AG": {2026: "https://www.sak.ch/downloads/strom/strompreise/sak-tarife-2026.json", 2027: "https://www.sak.ch/downloads/strom/strompreise/sak-tarife-2027.json"},
    "Stadtwerke Wetzikon": {2026: "https://sec-energy.ch/tarifdaten/wetzikon/Tarifdaten_2026_Stadtwerke_Wetzikon.json", 2027: "https://sec-energy.ch/tarifdaten/wetzikon/tariffs-10675012345-stadtwerke-wetzikon-2027.json"},
    "Technische Betriebe Birmenstorf": {2026: "https://energieverbrauch.ch/download/Tarife/Technische_Betriebe_Birmenstorf_2026.json"},
    "Technische Betriebe Flawil (TBF)": {2026: 'https://www.tbflawil.ch/tarifkommunikation/2026_tariffs.json', 2027: 'https://www.tbflawil.ch/tarifkommunikation/2027_tariffs.json'},
    "Technische Betriebe Glarus Nord (TBGN)": {2026: "https://www.tbgn.ch/images/T2026/TBGN-Strom-Tarife-2026.json"},
    "Technische Betriebe Oberentfelden": {2026: "https://www.oberentfelden.ch/sites/default/files/2025-08/Tarife_Technische_Betriebe_Oberentfelden_2026.json"},
    "Technische Betriebe Weinfelden AG": {2026: "https://tbweinfelden.ch/stromtarife/stromtarife-2026.json", 2027: "https://www.tbweinfelden.ch/stromtarife/stromtarife-2027.json"},
    "Technische Gemeindebetriebe Wängi": {2026: "https://tbwaengi.ch/userdata/files/preise_2026_tbwaengi_maschinenlesbar.json", 2027: "https://www.tbwaengi.ch/userdata/dateien/json_dateien/preise-2027-tbwaengi-maschinenlesbar.json"},
    "Technische Werke Eschlikon": {2026: "https://www.eschlikon.ch/public/upload/assets/5485/preise-2026-tweschlikon_maschinenlesbar.json", 2027: "https://sec-energy.ch/tarifdaten/eschlikon/tariffs-10011012345-technische-werke-eschlikon-2027.json"},
    "Thurwerke AG": {2026: "https://thurwerke.ch/wp-content/uploads/2025/08/Tarifblatt_2026_Thurwerke_AG.json", 2027: "https://thurwerke.ch/wp-content/uploads/2026/08/Tarife_Thurwerke_AG_2026-2027.json"},
    "Viteos SA": {2026: "https://www.viteos.ch/wp-content/tarifs/tarifs_electriques_2026.json", 2027: "https://www.viteos.ch/wp-content/tarifs/tarifs_electriques.json"},
    "Werke Horgen": {2026: "https://sec-energy.ch/tarifdaten/horgen/Tarifdaten_2026_Werke_Horgen.json", 2027: "https://sec-energy.ch/tarifdaten/horgen/tariffs-10297012345-werke-horgen-2027.json"},
    "Werke Wangen-Brüttisellen": {2026: "https://www.werkewb.ch/tarife-elcom/WWB_20250830_tariffs.json", 2027: "https://www.werkewb.ch/tarife-elcom/WWB_20260831_tariffs.json"},
    "Werke am Zürichsee AG (Erlenbach)": {2026: "https://werkezuerichsee.ch/wp-content/uploads/2026_erlenbach.json", 2027: "https://www.werkezuerichsee.ch/strompreise-maschinenlesbar/2027_erlenbach.json"},
    "Werke am Zürichsee AG (Küsnacht)": {2026: "https://werkezuerichsee.ch/wp-content/uploads/2026_kuesnacht.json", 2027: "https://www.werkezuerichsee.ch/strompreise-maschinenlesbar/2027_kuesnacht.json"},
    "Werke am Zürichsee AG (Zollikon)": {2026: "https://werkezuerichsee.ch/wp-content/uploads/2026_zollikon.json", 2027: "https://www.werkezuerichsee.ch/strompreise-maschinenlesbar/2027_zollikon.json"},
    "eug Elektra Untergäu Genossenschaft": {2026: "https://www.eug.ch/media/ziwps1q4/20250807_tariffs_final.json"},
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

def available_dsos(sources, day):
    """Only offer explicit current-year maps; never guess a setup source."""
    return {name: source for name, source in sources.items()
            if not isinstance(source, dict) or day.year in source}


@config_entries.HANDLERS.register(DOMAIN)
class SECEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SECEnergyOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Erster Schritt: DSO (Stromversorger) auswählen"""
        errors = {}
        choices = available_dsos(PREDEFINED_DSOS, dt_util.now().date())
        
        if user_input is not None:
            dso_selection = user_input.get("dso")
            
            if dso_selection not in choices:
                return self.async_abort(reason="no_tariffs")

            if dso_selection == "Custom / Other":
                # Benutzer will eigene URL eingeben
                return await self.async_step_custom_url()
            
            # Vordefinierter DSO
            self.context["dso_name"] = dso_selection
            self.context["dso_key"] = dso_selection
            return await self.async_step_tariff()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("dso", default="Stadtwerke Wetzikon"): vol.In(list(choices)),
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
                            
                            # Schema-Validierung
                            schema_errors = validate_schema(data)
                            if schema_errors:
                                _LOGGER.error("Schema-Validierung fehlgeschlagen: %s", schema_errors)
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
            # Persist validity of the selected tariff, not an unrelated entry.
            selected = select_tariff(self.context.get("document", {}), user_input["tariff"], dt_util.now().date())
            if selected is None:
                return self.async_abort(reason="no_tariffs")
            self.context["valid_until"] = selected.get("endDate")
            return self.async_create_entry(
                title=user_input.get("name", dso_name),
                data={
                    "name": user_input.get("name", dso_name),
                    "dso_url": self.context.get("resolved_url") or dso_url,
                    "dso_key": self.context.get("dso_key"),
                    "resolved_url": self.context.get("resolved_url") or dso_url,
                    "valid_until": self.context.get("valid_until"),
                    "dso_name": dso_name,
                    "tariff": user_input["tariff"],
                    "scan_interval": user_input.get("scan_interval", 86400),
                }
            )
        
        # Lade Tarife von der API
        tariff_choices = {}
        text = None
        try:
            source = PREDEFINED_DSOS.get(self.context.get("dso_key"), dso_url)
            day = dt_util.now().date()
            resolved_url, data = await resolve_document(source, day, fetch_document, validate_schema)
            self.context["resolved_url"] = resolved_url
            self.context["document"] = data
            self.context["valid_until"] = None

            for t in data.get("tariffs", []):
                if not covers(t, day):
                    continue
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
