# Birwinken 2026 – abgeleitete Bezugstarife

Erstellt/geprüft 2026-11-01. Dies ist eine Rekonstruktion aus dem offiziellen PDF, **kein offizieller JSON-Feed** und noch kein gehosteter HA-Feed. Die Veröffentlichung als GitHub-Pages-Feed und die 2026-Katalogeinbindung erfolgen separat. Der bestehende offizielle 2027-Feed bleibt unverändert.

## Quellen und Identität
- PDF: https://www.birwinken.ch/public/upload/assets/2240/Tarifblatt_2026_v2_neu.pdf?fp=1
- SHA256 PDF: 0db4e278a2d52ffdaeb0cd1a38ae89def40dc62c5f988ba13c718e1b1f7956f2
- Schema: https://tariffconverter.strom.ch/ch-electricity-tariffs-openapi.yml (1.0.1)
- SHA256 Schema: 34f53db1025bb5bd3f6cd03c604d969918109b66395bdcc2ef73b2931677d479
- Identität aus offizieller Betreiberdatei (nur Identität/Netzebene, keine Preise/Zeiten übernommen): https://www.birwinken.ch/public/upload/assets/2496/Tarife%202027_maschinenlesbar.json?fp=2
- DSO Technische_Werke_der_Gemeinde_Birwinken, 10455012345. Anders als die 2027-Quelle enthält das Ergebnis die ID korrekt als Integer, ISO-Datumswerte und keine ungültige Spannungsebene 0.
- Gemeinde Birwinken 4901 zusätzlich über geo.admin.ch swissboundaries3d (municipality.json) bestätigt.
- Vorhergehende Research-Karte fand keinen 2026-Feed an ihren geprüften URLs. Das beweist nicht, dass niemals einer existiert hat.

## PDF-Seite 1: Zuordnung und Mapping
Die gerenderte Originalseite bestätigt drei Spalten: Haushalt <100 MWh/a, Industrie >100 MWh/a, Baustrom. Für exakt 100 MWh/a wird keine neue Zuordnung erfunden.
Alle Preise exkl. MWST; Division Rp/kWh durch 100 mit Decimal.

| Gruppe | electricity CHF/kWh | grid CHF/kWh | Gemeinde CHF/kWh | Total Rp/kWh | grid.base CHF/M | metering.base CHF/M | Leistung CHF/kW/M |
|---|---:|---:|---:|---:|---:|---:|---:|
| Haushalt <100 MWh/a | 0.152 | 0.1043 | 0.001 | 25.73 | 10.50 | 4.50 | nicht angegeben |
| Industrie >100 MWh/a | 0.146 | 0.0653 | 0.001 | 21.23 | 10.50 | 4.50 | 10.00 |
| Baustrom | 0.160 | 0.2453 | 0.001 | 40.63 | 0.00 | 0.00 | nicht angegeben |

- electricity.energy = Energie (14.10/13.50/14.90 Rp) + EE-Aufwertung 1.10 Rp in ALLEN drei Gruppen. Die Aussage „optional/nicht Baustrom“ im Research-Zwischenstand ist falsch: PDF-Basisangebot enthält die Aufwertung, Totalsummen bestätigen dies.
- grid.energy = Netznutzung (7.40/3.50/21.50) + SDL 0.27 + solidarisierte Kosten 0.05 + Stromreserve 0.41 + KEV 2.30 Rp.
- Gemeindeabgabe ausschließlich regional_fees.municipalityTaxes[].municipalityEnergy.
- Constant-Preise sind laut Schema jeweils EIN aggregierter Eintrag mit months=[], weekdays=[], from=to=00:00. Komponenten sind keine additiven, zeitlich überlappenden Einträge im energy-Array. Die gegenteilige Empfehlung im Research-Handoff wurde korrigiert.
- grid auf Netzebene 7 (Niederspannung), Industrie-Leistung allein bei Industrie.
- standardBasegroup true nur je einmal für Haushalt electricity/grid; sonst false.
- 12 eindeutig benannte Tarife: vier Tarifarten pro Kundengruppe. Verbraucher wählen zusammengehörige Gruppen, summieren nicht alle zwölf Tarife.
- Grundgebühr + Messtarif = 15.00 CHF/M exkl. MWST, nicht 16.22 (PDF-Bruttowert).

## Abgrenzung
PDF-Seite 2: PV-Rücklieferung/Referenzmarktpreise und optionale Naturstromprodukte werden nicht als fixe Bezugstarife oder refundStorage modelliert. Temporärer Baustromkasten (Montage/Miete) ist laut Fußnote separat, ohne bezifferten Preis; nicht erfunden. Keine HT/NT-Zeiten aus 2027 übernehmen. Keine Behauptung vollständiger Abdeckung sämtlicher PDF-Sonderprodukte.

## Reproduktion und Tests

Das geprüfte Artefakt aus t_a8ee591b wurde unverändert übernommen; keine zweite Tarifrekonstruktion. Originalquellen liegen unter `tariffs/birwinken/sources/2026/` (PDF, Schema-Snapshot, Identitätsdatei und Gemeindeantwort). Die Quellen wurden am 2026-11-01 gesichert. Generator und Tests sind relativ zum Repository verankert und benötigen kein bestimmtes Arbeitsverzeichnis.

```sh
python3 scripts/generate_birwinken_2026.py
python3 tests/test_validate_schema.py
PYTHONPATH=tests python3 -m unittest discover -s tests
uv venv .venv
uv pip install --python .venv/bin/python pyyaml jsonschema
.venv/bin/python scripts/validate_birwinken_2026.py
```

Die separate OpenAPI-Prüfung nutzt den gesicherten offiziellen Schema-Snapshot inklusive Formatprüfung. Die normale Offline-Suite benötigt weiterhin keine zusätzlichen Python-Pakete. Die Regression prüft alle Gruppen, Komponenten, Monats-/Leistungsgebühren, konstante Filter und Jahresgrenzen gegen die echten Integrationsfunktionen mit bestehenden HA-Testdoubles (kein live Home Assistant).

SHA256 JSON: `ecbd523cc6dd8d48f7ce5c445207b37815b6462255896e80c166cdaaf231cf98`.

## Integrationsgrenzen / nachgelagerte Freigabe

Dies sind Daten, keine vollständige Gesamtpreis-Sensorunterstützung: Die Integration wählt einen Tarif, paart nicht automatisch alle vier Tarifarten und addiert Gemeinde-/Leistungsgebühren nicht automatisch zu einem vollständigen Bezugsgesamtpreis. Die hier geprüften PDF-Totale sind Datenprüfungen, keine Zusage einer entsprechenden Sensoranzeige. MWST muss gegebenenfalls genau einmal in der Darstellung berücksichtigt werden.

Kein Hosting oder Katalogwechsel in diesem PR. Die geplante Pages-URL ist vor Deployment **nicht live verifiziert**. Nach Merge folgen Hosting und ausschließlich der 2026-Jahreseintrag in t_1f1cc54a; der 2027-Pfad bleibt erhalten. Kein Merge oder Release ist durch diesen Daten-PR autorisiert. v1.1.1 setzt beide tatsächlichen Merges und verifiziertes Live-Hosting voraus.
