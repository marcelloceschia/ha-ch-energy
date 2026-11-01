# Muhen tariff fixture

`muhen_2026.json` is the unmodified response downloaded on 2026-10-31 from:

https://www.muhen.ch/public/upload/assets/3522/Tarife%20Elektrizit%C3%A4tswerk%20Muhen.json

HTTP 200; nine tariffs, with `dsoNumber` encoded as the string `10013012345`.
The official schema at https://tariffconverter.strom.ch/ch-electricity-tariffs-openapi.yml
still specifies an integer (11-digit VSE/AES identifier). String support in
this integration is a deliberate compatibility extension for published DSO
files, not an upstream specification change. No price data is transformed.

All nine tariffs encode the inclusive 2026 calendar-year boundaries as
`2026-01-01T00:00:00` and `2026-12-31T00:00:00` (local midnight, no offset).
`test_muhen_runtime.py` exercises coverage, resolution and selection on this
unmodified fixture, including both year edges. The runtime compatibility
extension accepts this exact midnight form, not arbitrary timestamps.
