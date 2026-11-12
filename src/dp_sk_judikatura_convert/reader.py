"""Reader of a nsud ``decision.json`` (port of the legacy SkDecisionReader.TryRead).

Accepts the raw OpenData body (an object, or an array-wrapped object), reads keys case-insensitively, coerces a numeric scalar to its digits, takes the
decision id from the body ``ID`` or, when that is blank (the live API sends ``""``), from the ``nsud/<id>/`` folder. The id must be digits only: it is
interpolated into paths and the legacy ``NsudJson`` guard against path traversal is kept. New against the legacy (P81-05): an empty ``obsah`` with a PDF
attachment (``subor``) is a decision whose text comes from the PDF, not a rejection.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from dp_sk_judikatura_convert.court import court_of, kolegium_name

if TYPE_CHECKING:
    from pathlib import Path

_ECLI_SHAPE = re.compile(r"^ECLI:SK:[A-Z0-9]+:\d{4}:[0-9A-Za-z.]+$")


@dataclass(frozen=True)
class Decision:
    """One decision as the source describes it; ``text`` is None for a PDF-only decision."""

    source_id: str
    court: str
    cislo: str
    senat: str | None
    ecli: str | None
    datum: date | None
    kolegium: str | None
    kolegium_nazov: str | None
    merito: str
    sudca: str | None
    text: str | None
    pdf: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rejected:
    """The file cannot become a decision: ``parse_error``, ``bad_id`` or ``no_text``."""

    reason: str


def digits_only(value: str | None) -> bool:
    """A decision id is ASCII digits only (path-traversal guard shared with the grab)."""
    return bool(value) and value is not None and value.isascii() and value.isdigit()


def _scalar(obj: dict[str, Any], name: str) -> str | None:
    for key, value in obj.items():
        if key.lower() == name.lower():
            if isinstance(value, bool):
                return str(value).lower()
            if isinstance(value, (str, int, float)):
                return str(value)
            return None
    return None


def _blank_to_none(value: str | None) -> str | None:
    return None if value is None or not value.strip() else value


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()) if value else None
    except ValueError:
        return None


def _object(body: Any) -> dict[str, Any] | None:
    if isinstance(body, list):
        return body[0] if body and isinstance(body[0], dict) else None
    return body if isinstance(body, dict) else None


def read_decision(path: Path, folder_id: str | None = None) -> Decision | Rejected:
    """Read one decision file. ``folder_id`` is the item folder name (default: the parent directory of the file)."""
    try:
        obj = _object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Rejected("parse_error")
    if obj is None:
        return Rejected("parse_error")

    source_id = _blank_to_none(_scalar(obj, "id"))
    if source_id is None:
        source_id = path.parent.name if folder_id is None else folder_id
    source_id = source_id.strip()
    if not digits_only(source_id):
        return Rejected("bad_id")

    cislo = _blank_to_none(_scalar(obj, "cislo"))
    if cislo is None:
        return Rejected("parse_error")
    text = _blank_to_none(_scalar(obj, "obsah"))
    pdf = _blank_to_none(_scalar(obj, "subor"))
    if text is None and pdf is None:
        return Rejected("no_text")

    ecli = _blank_to_none(_scalar(obj, "ecli"))
    warnings = ("odd_ecli",) if ecli is not None and not _ECLI_SHAPE.match(ecli.strip()) else ()
    kolegium = _blank_to_none(_scalar(obj, "kolegium"))
    return Decision(
        source_id=source_id,
        court=court_of(ecli, text),
        cislo=cislo.strip(),
        senat=_blank_to_none(_scalar(obj, "senat")),
        ecli=ecli.strip() if ecli else None,
        datum=_date(_scalar(obj, "datum")),
        kolegium=kolegium.strip() if kolegium else None,
        kolegium_nazov=kolegium_name(kolegium),
        merito=_scalar(obj, "merito") or "",
        sudca=_blank_to_none(_scalar(obj, "sudca")),
        text=text,
        pdf=pdf.strip() if pdf else None,
        warnings=warnings,
    )
