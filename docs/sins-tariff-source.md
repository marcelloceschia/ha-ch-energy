# Sins tariff source

Verified on 2026-11-01 against `origin/main` ae70d47.

- Catalogue name: Elektra Sins; SEC-Energy lists Elektrizitätsgenossenschaft Sins.
- Source: https://strompreisvergleich.ch/tarife/data/10346012345/tarife.json
- Attribution: https://sec-energy.ch/tools-daten/maschinenlesbare-tarifdaten?view=machine_readable&provider_debug_marks=0&q=Sins&stromjahr=2027
- GET: HTTP 200, application/json, no redirect; 20 tariffs covering
  2026-01-01–2026-12-31 and 2027-01-01–2027-12-31.
- Raw SHA-256: `65557ea338a195aa050e8eecc59c5c5acfc609667b5e4a4ed5fb9caed43b4384`.
- Previous operator-hosted 2026 URL still returns HTTP 404.

## Compatibility and source decision

This is a third-party source linked by SEC-Energy, not an operator-hosted
publication. The task was unblocked with explicit approval to accept
`dsoNumber` strings. The source passes the integration validator unchanged,
using the existing compatibility support merged in PR #5: integers or exactly
11 ASCII digits as text. No normalization, mutation, or additional validator
relaxation is introduced here.

The official OpenAPI 1.0.1 still requires an integer: independent validation
of the unchanged file has exactly one error at `dsoNumber` (`"10346012345"`).
It is integration-compatible, **not strictly official-schema-conformant**.
The catalogue's third-party guard allows only this exact Sins URL; other
third-party sources still require separate decisions.

Both integer year keys point to the same year-independent multi-year file.
Offline tests cover unmodified validation and real tariff selection on
2026-12-31 / 2027-01-01; 2028 is not claimed as covered. HTTP 200 was verified
in both research runs (2026-10-31 and 2026-11-01), but long-term availability
or an SLA cannot be guaranteed. The fixture is the unchanged downloaded body.

Existing V2 entries retaining the Elektra Sins catalogue key pick up the new
source at refresh. This patch does not add migration for manually entered
custom URLs or older stored URLs that no longer match the catalogue.
