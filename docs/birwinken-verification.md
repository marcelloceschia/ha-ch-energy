# Birwinken Issue #15 — verification and scope

## Change

Accept valid naive midnight ISO datetime boundaries in addition to existing date-only boundaries. Both remain inclusive calendar dates, including 31 December. Arbitrary suffixes, invalid calendar dates, non-midnight times, timezone offsets and boolean boundaries are rejected. Existing absent/null/empty boundaries stay open. No validator or catalogue change.

Missing, null and empty months/weekdays mean unrestricted in both current-price selection and next-boundary calculation. Explicit filters remain effective. The existing minimum-price fallback and same-day boundary algorithm are otherwise unchanged; a boundary does not necessarily mean a numerically different price.

Fixture: unmodified operator response archived from upstream PM attachment; official URL https://www.birwinken.ch/public/upload/assets/2496/Tarife%202027_maschinenlesbar.json?fp=2 . No assertion about historical format changes.

## Executed evidence

- Before changes: 53 existing tests pass. All six official datetime-boundary subtests fail. Synthetic Monday 04 January 2027 12:00 yields 0.141 instead of 0.25 without months; null filters raise TypeError.
- After changes: regression covers all six tariffs, first/last valid days, future/expired days, malformed dates, all three unrestricted filter representations and explicit restrictions.
- Real coordinator and current/base sensor getter code is exercised via existing AST harness with HA boundary doubles. This is not an installed Home Assistant or browser/dashboard test.
- Simulated 01 November 2026: each selection has current price None, tariff None, data_expired=True; future document retained, warning/repair semantics unchanged.
- Simulated 04 January 2027: each selection active, data_expired=False; selected component values below. Original prices preserved unchanged in coordinator raw data.

| Selected tariff | Current component CHF/kWh | Base CHF/month |
|---|---:|---:|
| Haushalt (E) | 0.141 | 0 |
| Haushalt (N) | 0.0925 | 10.5 |
| Industrie NS (E) | 0.135 | 0 |
| Industrie NS (N) | 0.0535 | 10.5 |
| Baustrom (E) | 0.149 | 0 |
| Baustrom (N) | 0.2335 | 0 |

## Fees and product boundary

These are selected component prices, NOT a complete electricity bill. Existing current/forecast sensors read the selected tariff's energy only. Base sensor reads selected prices.base separately (tested). The three N tariffs additionally contain municipalityEnergy 0.001 CHF/kWh for BFS 4901, not included in current-price sensor. Industrie NS (N) has power 10 CHF/kW/month, not represented by a dedicated sensor. Reactive power and cantonal tax arrays are empty; refundStorage is zero. Data is preserved, not double-counted or automatically combined across E/N tariffs.

Full support needs a separate product decision: explicit E/N pairing, municipality selection/tax inclusion, demand measurement for kW/month, and clear total/component sensor semantics. This PR deliberately does not invent those decisions or claim total-price support. Separate 2026 tariff/hosting pipeline remains untouched (t_e8d3c3cd).

## Outstanding acceptance blocker

Environment probe: Home Assistant Python package absent and no HASS/HOME_ASSISTANT/HA_URL/HA_TOKEN connection variables supplied. No HA test endpoint or dashboard login has been provided by the task. Actual HA entity registration, dashboard rendering, and 2027 clock simulation on a real instance remain UNVERIFIED. Supply an authorized disposable HA instance (or approve provisioning one) to finish that acceptance criterion. No deployment, merge, release or issue reply was performed.
