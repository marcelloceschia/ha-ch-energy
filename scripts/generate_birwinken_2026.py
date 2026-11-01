"""Reconstruct the three standard consumption tariffs; all prices exclude VAT."""
import json
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'tariffs/birwinken/sources/2026'

SOURCE = 'https://www.birwinken.ch/public/upload/assets/2240/Tarifblatt_2026_v2_neu.pdf?fp=1'

def price(value, unit='CHF/kWh'):
    return {'months': [], 'weekdays': [], 'from': '00:00', 'to': '00:00', 'price': float(value), 'priceUnit': unit}

def generate():
    identity = json.loads((EVIDENCE / 'identity-2027.json').read_text())
    assert int(identity['dsoNumber']) == 10455012345
    tariffs = []
    for group, energy, network, base, meter, power, expected in [
        ('Haushalt <100 MWh/a','14.10','7.40','10.50','4.50',None,'25.73'),
        ('Industrie >100 MWh/a','13.50','3.50','10.50','4.50','10.00','21.23'),
        ('Baustrom','14.90','21.50','0.00','0.00',None,'40.63')]:
        electricity = (D(energy)+D('1.10'))/100
        grid = sum(map(D,[network,'0.27','0.05','0.41','2.30']))/100
        assert (electricity+grid+D('0.001'))*100 == D(expected)
        prices = {
            'electricity': {'energy': [price(electricity)]},
            'grid': {'base': {'price':float(base),'priceUnit':'CHF/M'},'energy':[price(grid)]},
            'metering': {'base': {'price':float(meter),'priceUnit':'CHF/M'}},
            'regional_fees': {'municipalityTaxes': [{'municipalityNumber':4901, 'municipalityName':'Birwinken','municipalityEnergy':[price(D('0.001'))]}]},
        }
        if power:
            prices['grid']['power'] = [price(D(power),'CHF/kW/M')]
        explanations = {
            'electricity': f'Energie {energy} + EE-Aufwertung 1.10 Rp/kWh (Basisangebot).',
            'grid': f'Netznutzung {network} + SDL 0.27 + solidarisierte Kosten 0.05 + Stromreserve 0.41 + Netzzuschlag KEV 2.30 Rp/kWh; Grundgebühr {base} CHF/Monat.' + (f' Leistung {power} CHF/kW/Monat.' if power else ''),
            'metering': f'Messtarif {meter} CHF je Monat.',
            'regional_fees': 'Abgabe an Gemeindewesen 0.10 Rp/kWh; nicht in grid.energy enthalten.'
        }
        for kind, values in prices.items():
            tariff = {
                'tariffName': f'{group} 2026 ({kind})',
                'tariffType':kind,
                'standardBasegroup':group.startswith('Haushalt') and kind in ('electricity','grid'),
                'tariffForm':'constant',
                'startDate':'2026-01-01', 'endDate':'2026-12-31',
                'customerType':group,
                'comment': f'Abgeleitete Rekonstruktion, kein offizieller JSON-Feed. Quelle: {SOURCE}, Seite 1. Alle Preise exkl. MWST. {explanations[kind]} Keine HT/NT-Zeiten im Bezugstarif angegeben.',
                'prices':values,
            }
            if kind == 'grid': tariff['customerVoltageLevel']=7
            tariffs.append(tariff)
    return {'dsoName':identity['dsoName'],'dsoNumber':int(identity['dsoNumber']),'tariffs':tariffs}

if __name__ == '__main__':
    output=(ROOT / 'tariffs/birwinken/2026_tariffs.json')
    output.write_text(json.dumps(generate(),ensure_ascii=False,indent=2)+'\n')
    print(f'{output}: 12 tariffs written')
