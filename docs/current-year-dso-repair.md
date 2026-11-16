# Current-year DSO catalogue repair

The setup list is rebuilt on every opening using Home Assistant's local date.
Year maps without an explicit current-year URL are hidden; direct submissions of
hidden choices are rejected. Yearless sources and Custom / Other remain.
This is a configuration filter, not a live availability probe. Existing entries
and the runtime resolver retain their existing fallback behaviour.

IBI has only a verified 2027 source: hidden in 2026, offered from 2027-01-01.
Muhen's official 2026 URL and Wettingen's official 2026/2027 URL are restored.
Gossau uses the exact strompreisvergleich.ch source approved by merged PR #7,
not the different strompreiswechsel.ch domain in the research handoff.

The versioned `scripts/check_dso_urls.py` supports integer year maps without
importing HA. Run from the repository or set `SEC_ENERGY_REPO` to the clone root.
It probes HTTP, JSON parsing and a non-empty tariffs array; it is not a complete
production-schema or temporal-coverage validator. Unavailable year maps are
reported separately, not counted as healthy. Network failures exit 1.

Live run 2026-11-01: **90/93 gesund, 3 defekt, 1 ohne aktuelle Jahres-URL**.
Arni needs source approval; IWB needs a valid document/parser decision. Sins is
already handled separately by PR #16 (not merged at verification time).
No false 94/94 claim, no parser relaxation and no new Arni third-party approval.
The legacy skill checker was explicitly requested and synchronized with this
versioned copy; it no longer targets an unrelated hardcoded clone.

## Follow-up verified on 2026-11-16

Arni-Islisberg now uses the SEC-listed strompreisvergleich.ch document for both
2026 and 2027. It contains nine tariffs per year and passes the integration's
validator. Its `dsoNumber` is an 11-digit string; the integration accepts that
known publisher deviation, while the strict official OpenAPI schema expects an
integer.

IBI remains future-only with its verified 2027 source and stays hidden during
2026 setup. No verified 2026 JSON source was found in the documented SEC/IBI
search scope.

IWB is intentionally not switched to the proposed replacement yet. Besides
being two concatenated JSON documents, each part has 20 `regional_fees` tariffs
without `municipalityTaxes`, so the current production validator rejects them.
The old configured URL still returns HTTP 404; a separate compatible source or
a deliberate parser/schema repair is still required.
