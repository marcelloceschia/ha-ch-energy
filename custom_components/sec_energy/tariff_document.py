"""Decode SEC-Energy documents, including IWB's concatenated year files."""
from datetime import date
import json
from typing import NoReturn


def parse_tariff_document(text, *, today=None):
    """Return a single tariff document; never silently discard trailing data.

    IWB publishes consecutive complete objects (2027 followed by 2026), not
    a JSON array. Only accept that known format for the same IWB identity,
    and select exactly one document whose entire tariff period is current.
    Ordinary, valid JSON documents retain their existing behaviour.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        if error.msg != "Extra data":
            raise

    decoder = json.JSONDecoder()
    documents = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        document, position = decoder.raw_decode(text, position)
        documents.append(document)

    def fail(message) -> NoReturn:
        raise json.JSONDecodeError(message, text, 0)

    if not all(
        isinstance(document, dict)
        and document.get("dsoName") == "IWB"
        and document.get("dsoNumber") == 10167012345
        and isinstance(document.get("tariffs"), list)
        and document["tariffs"]
        for document in documents
    ):
        fail("Unsupported concatenated tariff documents")

    current_date = today if today is not None else date.today()
    candidates = []
    for document in documents:
        try:
            periods = [
                (date.fromisoformat(tariff["startDate"]),
                 date.fromisoformat(tariff["endDate"]))
                for tariff in document["tariffs"]
            ]
        except (KeyError, TypeError, ValueError):
            fail("Invalid tariff dates in concatenated IWB documents")
        if any(start > end for start, end in periods):
            fail("Reversed tariff dates in concatenated IWB documents")
        if all(start <= current_date <= end for start, end in periods):
            candidates.append(document)

    if len(candidates) != 1:
        fail("Expected exactly one current IWB tariff document")
    return candidates[0]
