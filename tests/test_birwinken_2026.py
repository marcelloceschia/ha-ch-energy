import json
from pathlib import Path
import unittest
from decimal import Decimal as D
import sys
from test_validate_schema import validate_schema

class BirwinkenTests(unittest.TestCase):
    def test_reproducible_generator_and_source_hashes(self):
        import hashlib
        import importlib.util
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('birwinken_generator', root / 'scripts/generate_birwinken_2026.py')
        assert spec is not None and spec.loader is not None
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        actual = (root / 'tariffs/birwinken/2026_tariffs.json').read_bytes()
        expected = (json.dumps(generator.generate(), ensure_ascii=False, indent=2) + '\n').encode()
        self.assertEqual(actual, expected)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), 'ecbd523cc6dd8d48f7ce5c445207b37815b6462255896e80c166cdaaf231cf98')
        for name, digest in [('source.pdf', '0db4e278a2d52ffdaeb0cd1a38ae89def40dc62c5f988ba13c718e1b1f7956f2'),
                             ('schema.yml', '34f53db1025bb5bd3f6cd03c604d969918109b66395bdcc2ef73b2931677d479')]:
            self.assertEqual(hashlib.sha256((root / 'tariffs/birwinken/sources/2026' / name).read_bytes()).hexdigest(), digest)

    def test_year_boundaries_and_constant_runtime_prices(self):
        from datetime import date, datetime
        from test_year_change import tariffs
        from test_year_coordinator import load_code
        ns = load_code()
        document = json.loads((Path(__file__).resolve().parents[1] / 'tariffs/birwinken/2026_tariffs.json').read_text())
        for tariff in document['tariffs']:
            with self.subTest(name=tariff['tariffName']):
                for day in (date(2026, 1, 1), date(2026, 12, 31)):
                    self.assertTrue(tariffs.covers(tariff, day))
                for day in (date(2025, 12, 31), date(2027, 1, 1)):
                    self.assertFalse(tariffs.covers(tariff, day))
                if tariff['tariffType'] in ('electricity', 'grid'):
                    expected = tariff['prices']['energy'][0]['price']
                    for month in range(1, 13):
                        for hour in (0, 12, 23):
                            self.assertEqual(ns['get_current_price'](tariff, datetime(2026, month, 1, hour)), expected)

    def test_complete_standard_tariffs(self):
        path = Path(__file__).resolve().parents[1] / 'tariffs/birwinken/2026_tariffs.json'
        self.assertTrue(path.exists(), 'Generated 2026 tariff document missing')
        data = json.loads(path.read_text())
        self.assertEqual(validate_schema(data), [])
        self.assertIs(type(data['dsoNumber']), int)
        self.assertEqual(data['dsoNumber'], 10455012345)
        tariffs = data['tariffs']
        self.assertEqual(len(tariffs),12)
        self.assertEqual(len({t['tariffName'] for t in tariffs}),12)
        for kind in ['electricity','grid','metering','regional_fees']:
            self.assertEqual(sum(t['standardBasegroup'] for t in tariffs if t['tariffType']==kind), 1 if kind in ['electricity','grid'] else 0)
        for group, energy, grid, total, base, power in [
            ('Haushalt <100 MWh/a', '0.152','0.1043','0.2573','10.50',None),
            ('Industrie >100 MWh/a','0.146','0.0653','0.2123','10.50','10'),
            ('Baustrom','0.16','0.2453','0.4063','0',None)]:
            with self.subTest(group=group):
                ts = {t['tariffType']: t for t in tariffs if t['customerType']==group}
                self.assertEqual(len(ts),4)
                for t in ts.values():
                    self.assertEqual((t['startDate'],t['endDate']),('2026-01-01','2026-12-31'))
                    self.assertEqual(t['tariffForm'],'constant')
                    self.assertNotIn('refundStorage',t['prices'])
                    self.assertIn('Rekonstruktion',t['comment'])
                e = ts['electricity']['prices']['energy']
                g = ts['grid']['prices']['energy']
                self.assertEqual(len(e),1)
                self.assertEqual(len(g),1)
                self.assertEqual(D(str(e[0]['price'])),D(energy))
                self.assertEqual(D(str(g[0]['price'])),D(grid))
                tax = ts['regional_fees']['prices']['municipalityTaxes'][0]
                self.assertEqual((tax['municipalityNumber'],tax['municipalityName']),(4901,'Birwinken'))
                self.assertEqual(D(str(tax['municipalityEnergy'][0]['price'])),D('0.001'))
                self.assertEqual(D(energy)+D(grid)+D('0.001'),D(total))
                for entry in e+g+tax['municipalityEnergy']+ts['grid']['prices'].get('power',[]):
                    self.assertEqual((entry['months'],entry['weekdays'],entry['from'],entry['to']),([],[],'00:00','00:00'))
                self.assertEqual(ts['grid']['customerVoltageLevel'],7)
                self.assertEqual(ts['grid']['prices']['base'],{'price':float(base),'priceUnit':'CHF/M'})
                self.assertEqual(ts['metering']['prices']['base'],{'price':0 if base=='0' else 4.5,'priceUnit':'CHF/M'})
                if power is None:
                    self.assertNotIn('power',ts['grid']['prices'])
                else:
                    self.assertEqual(ts['grid']['prices']['power'][0]['price'],10)
                    self.assertEqual(ts['grid']['prices']['power'][0]['priceUnit'],'CHF/kW/M')

if __name__=='__main__': unittest.main(verbosity=2)
