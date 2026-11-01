"""Date-aware tariff selection and Jahres-Map resolution (HA-independent)."""
from datetime import date
import logging

_LOGGER = logging.getLogger(__name__)


def source_candidates(source, day):
    """Jahres-Map: exact year or substitution, Q4 next year, previous grace.

    Only the newest known entry is used for guesses. Publication datestamps
    are not inferred: every guessed response still needs schema/date checks.
    Yearless strings (including custom URLs) are fetched unchanged.
    """
    if not isinstance(source, dict):
        return [source]
    if not source:
        return []
    latest = max(source)
    years = [day.year] + ([day.year + 1] if day.month >= 10 else []) + [day.year - 1]
    return list(dict.fromkeys(
        source[y] if y in source else source[latest].replace(str(latest), str(y))
        for y in years))


def match_dso(url, sources):
    """Recover identity without freezing a copy of the source catalogue."""
    for key, source in sources.items():
        if isinstance(source, dict):
            if url in source.values():
                return key
        elif source == url:
            return key
    return None


async def resolve_document(source, day, fetch, validate, name=None):
    """Validate candidates, including selected tariff and temporal coverage.

    Q4 next-year documents may be downloaded, never used as today's tariff.
    The coordinator separately retains today's last-known tariff.
    """
    future = None
    for url in source_candidates(source, day):
        try:
            document = await fetch(url)
            if not isinstance(document, dict) or validate(document):
                continue
            entries = [t for t in document['tariffs'] if name is None or t.get('tariffName') == name]
            if any(covers(t, day) for t in entries):
                return url, document
            if day.month >= 10 and any(covers(t, date(day.year + 1, 1, 1)) for t in entries):
                future = future or (url, document)
        except (OSError, ValueError, TypeError, KeyError, TimeoutError) as err:
            _LOGGER.debug('Rejected tariff source %s: %s', url, err)
    if future:
        return future
    raise ValueError('No valid tariff source available')


def _boundary_date(value):
    """Accept dates and Muhen's exact local-midnight boundary form only.

    Midnight encodes an inclusive calendar date, not a UTC instant. Do not
    truncate arbitrary timestamps, timezone offsets or trailing garbage.
    """
    if isinstance(value, str) and len(value) == 19 and value.endswith('T00:00:00'):
        value = value[:10]
    return date.fromisoformat(value)


def covers(tariff, day):
    """Missing boundaries are open; malformed boundaries are never current."""
    try:
        start = _boundary_date(tariff["startDate"]) if tariff.get("startDate") else date.min
        end = _boundary_date(tariff["endDate"]) if tariff.get("endDate") else date.max
        return start <= day <= end
    except (TypeError, ValueError):
        return False


def select_tariff(document, name, day):
    """Select a matching, currently valid tariff; never a future price."""
    return next((t for t in document.get("tariffs", [])
                 if t.get("tariffName") == name and covers(t, day)), None)
