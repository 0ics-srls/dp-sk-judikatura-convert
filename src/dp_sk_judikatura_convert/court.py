"""Court and chamber of a nsud decision. The API has no court field: the ECLI court code wins, then the ``Sud:`` header line of the text, then NSSR."""
from __future__ import annotations

import re
import unicodedata

DEFAULT_COURT = "NSSR"
_ECLI_COURT = re.compile(r"^ECLI:SK:([A-Z0-9]+):", re.IGNORECASE)
_HEADER_LINE = re.compile(r"^\s*s[uú]d\s*:\s*(?P<name>.+)$", re.IGNORECASE | re.MULTILINE)
_KNOWN = {"NSSR", "NSSSR"}
_KOLEGIUM = {"1": "Občianskoprávne", "2": "Obchodnoprávne", "3": "Správne", "4": "Trestnoprávne"}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def court_of(ecli: str | None, obsah: str | None) -> str:
    """NSSR or NSSSR. An ECLI of another court (a lower court) is not a Supreme Court code, so the default applies."""
    if ecli:
        match = _ECLI_COURT.match(ecli.strip())
        if match and match.group(1).upper() in _KNOWN:
            return match.group(1).upper()
    if obsah:
        header = _HEADER_LINE.search(obsah[:2000])
        if header:
            name = _fold(header.group("name"))
            if "najvyssi spravny sud" in name:
                return "NSSSR"
            if "najvyssi sud" in name:
                return "NSSR"
    return DEFAULT_COURT


def kolegium_name(code: str | None) -> str | None:
    """Slovak name of the chamber code (1 civil, 2 commercial, 3 administrative, 4 criminal); unknown codes have no name."""
    return _KOLEGIUM.get(code.strip()) if code else None
