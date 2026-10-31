"""Date-aware tariff selection and hybrid source resolution (HA-independent)."""
from datetime import date
import logging
import re

_LOGGER = logging.getLogger(__name__)


def source_candidates(source, day):
    """Exact year first, Q4 next year, then previous-year grace."""
    years = [day.year] + ([day.year + 1] if day.month >= 10 else []) + [day.year - 1]
    if isinstance(source, dict):
        return list(dict.fromkeys(source[y] for y in years if y in source))
    if '{year}' in source:
        return [source.replace('{year}', str(y)) for y in years]
    return [source]


def match_dso(url, sources):
    """Recover identity without freezing a copy of the source catalogue."""
    for key, source in sources.items():
        if isinstance(source, dict):
            if url in source.values():
                return key
        elif source == url or ('{year}' in source and re.fullmatch(
                re.escape(source).replace(r'\{year\}', r'\d{4}'), url or '')):
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


def covers(tariff, day):
    """Missing boundaries are open; malformed boundaries are never current."""
    try:
        start = date.fromisoformat(tariff["startDate"]) if tariff.get("startDate") else date.min
        end = date.fromisoformat(tariff["endDate"]) if tariff.get("endDate") else date.max
        return start <= day <= end
    except (TypeError, ValueError):
        return False


def select_tariff(document, name, day):
    """Select a matching, currently valid tariff; never a future price."""
    return next((t for t in document.get("tariffs", [])
                 if t.get("tariffName") == name and covers(t, day)), None)
