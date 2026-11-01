# Wettingen combined-year regression fixture

Source: https://www.energiewettingen.ch/upload/rm/20/26/20260824-enw-2027-tariffs-1.json

Retrieved 2026-11-01T21:47:07Z with a User-Agent, HTTP 200.
Raw response SHA-256: `2f165493516ae161c0bbf2d02990cdcd80b35d7104f35b0a042929cba98af576`.
`wettingen_2026_2027.json` preserves the parsed document, pretty-printed.
The live response contains 20 tariffs: ten bounded 2026-01-01–2026-12-31
and ten bounded 2027-01-01–2027-12-31. The filename alone does not identify
all years included. The catalogue intentionally uses this URL for both years.

`test_wettingen.py` validates the offline fixture, both catalogue keys, every
published tariff's inclusive dates/resolution/selection and rejection outside
its year. A separate derived same-name/different-price regression checks the
year rollover without a first-entry/minimum-price false positive. No network
is needed for these tests, and no complete energy+grid/fees or live HA UI claim
is made.
