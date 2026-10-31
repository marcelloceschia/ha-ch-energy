# Energie Gossau AG: tariff source decision

Checked 2026-10-31 (UTC). This entry is **Energie Gossau AG, Gossau ZH**,
not Stadtwerke Gossau SG.

## Decision

Use https://strompreisvergleich.ch/tarife/data/10766012345/tarife.json
as the predefined source. It is an externally hosted publication, not a
DSO-owned endpoint. SEC-Energy explicitly lists this exact URL for Energie
Gossau AG, DSO number 10766012345:

https://sec-energy.ch/tools-daten/maschinenlesbare-tarifdaten/versorger/energie-gossau-ag/2027/h4/standard

The portal homepage https://strompreisvergleich.ch/ also lists the JSON;
its privacy link points to encontrol.ch. Energie Gossau's own website links
to gossau.encontrol.ch as its customer portal, but this does **not** establish
a guarantee that the DSO itself publishes or endorses this specific JSON.
The source decision relies on SEC-Energy's explicit source attribution.

## Live observations

- Old DSO-hosted URL returned HTTP 404:
  https://energiegossau.ch/site/assets/files/1029/tarife_energie_gossau_ag_2026.json
- New URL returned HTTP 200 directly over HTTPS without authentication or
  redirects, with `Content-Type: application/json`.
- 90,570 bytes; SHA-256:
  `23f47c63b7d7ba3a96c927082a20dba4106c1d6c370603e11c27e44dbc915674`.
- `dsoName`: `Energie Gossau AG`; `dsoNumber`: `"10766012345"` (string).
- 30 tariffs, starting in 2026 and 2027. The checked document is stored
  unchanged in `tests/fixtures/gossau_2026_2027.json` for offline regression.
- HTTP `Last-Modified`: 2026-09-03 13:37:56 GMT; ETag present.

## Stability and validation limits

The identifier-based, year-independent URL already serves two tariff years,
so it avoids the old URL's annual filename rollover. It is preferable to the
known-dead URL, but there is no verified uptime history, SLA or promise of
future tariff updates. Last-Modified is server metadata, not proof of long-term
availability or data accuracy. The third-party dependency remains a risk;
recheck the URL, identity and year coverage at tariff-year changes and when
setup/update errors occur. Do not silently fall back to another operator.

The current official OpenAPI schema at
https://tariffconverter.strom.ch/ch-electricity-tariffs-openapi.yml declares
`dsoNumber` as integer. This publication therefore needs an explicit
compatibility exception, **not** a claim of strict official-schema compliance.
Task t_78ae60e5 owns the shared validator/schema change: accept exactly eleven
ASCII decimal digits as a string, preserving existing integer compatibility.
This task changes no schema rules. Its offline regression checks the actual,
unmodified Gossau document against the production validator; it must be
integrated together with that validator change.
