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
