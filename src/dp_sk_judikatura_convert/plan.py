"""The plan of one item (a month window of decision dates, or an explicit id list): what the ingest step loads (``planVersion`` 1).

A decision whose text stays empty is NOT written as an empty row: it goes to ``skipped`` with a declared reason (``parse_error``, ``bad_id``, ``no_text``,
``pdf_only_disabled``, ``pdf_missing``, ``pdf_unreadable``, ``ocr_empty``, ``ocr_unavailable``, ``ocr_failed``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dp_sk_judikatura_convert import ocr as ocr_mod
from dp_sk_judikatura_convert import pdftext
from dp_sk_judikatura_convert.piiguard import scan
from dp_sk_judikatura_convert.reader import Decision, Rejected, digits_only, read_decision

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

PLAN_VERSION = 1
FONTE = "nsud"


@dataclass
class ItemPlan:
    """One plan file."""

    rozhodnutia: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    coverage: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    pdf_only: int = 0
    ocr: int = 0

    def to_json(self) -> str:
        document = {
            "planVersion": PLAN_VERSION,
            "rozhodnutia": self.rozhodnutia,
            "skipped": self.skipped,
            "coverage": self.coverage,
            "warnings": self.warnings,
        }
        return json.dumps(document, ensure_ascii=False, indent=2)


def _sidecar(folder: Path) -> dict[str, Any]:
    try:
        loaded = json.loads((folder / "fetch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _text_of_pdf(pdf: Path, ocr_fn: Callable[[Path], str]) -> tuple[str, str]:
    """(text, text_source): the text layer, or OCR when the layer is not a document. Raises the declared errors of both."""
    text = pdftext.extract_text(pdf)
    if not ocr_mod.needs_ocr(text):
        return text, "pdf"
    return ocr_fn(pdf).replace(ocr_mod.FORM_FEED, "\n\n").strip(), "ocr"


def _pdf_text(attachment: Path, ocr_fn: Callable[[Path], str]) -> tuple[str, str, str | None]:
    """(text, text_source, skip reason): exactly one of text and reason is meaningful."""
    if not attachment.is_file():
        return "", "", "pdf_missing"
    reasons: dict[type[Exception], str] = {
        pdftext.PdfUnreadable: "pdf_unreadable", ocr_mod.OcrEmpty: "ocr_empty", ocr_mod.OcrUnavailable: "ocr_unavailable", ocr_mod.OcrFailed: "ocr_failed",
    }
    try:
        text, source = _text_of_pdf(attachment, ocr_fn)
    except tuple(reasons) as error:
        return "", "", reasons[type(error)]
    return (text, source, None) if text.strip() else ("", "", "no_text")


def _row(decision: Decision, text: str, text_source: str, sidecar: dict[str, Any]) -> dict[str, Any]:
    pdf_url = sidecar.get("pdfUrl") if isinstance(sidecar.get("pdfUrl"), str) else None
    page_url = sidecar.get("pageUrl") if isinstance(sidecar.get("pageUrl"), str) else None
    return {
        "fonte": FONTE,
        "source_id": decision.source_id,
        "court": decision.court,
        "cislo": decision.cislo,
        "senat": decision.senat,
        "ecli": decision.ecli,
        "datum_rozhodnutia": decision.datum.isoformat() if decision.datum else None,
        "kolegium": decision.kolegium,
        "kolegium_nazov": decision.kolegium_nazov,
        "merito": decision.merito,
        "sudca": decision.sudca,
        "text_raw": text,
        "text_source": text_source,
        "source_url": page_url or pdf_url,
        "pdf_url": pdf_url,
        "pii_flags": scan(text).total,
    }


def build_item_plan(
    raw_root: Path, index: dict[str, Any], item_meta: dict[str, Any], *, include_pdf_only: bool, ocr_fn: Callable[[Path], str],
) -> ItemPlan:
    """Plan of one item from the grab output: ``index`` lists the ids the grab took, ``raw_root/nsud/<id>/`` holds each decision."""
    plan = ItemPlan()
    for raw_id in index.get("ids", []):
        decision_id = str(raw_id)
        ref = f"{FONTE}:{decision_id}"
        if not digits_only(decision_id):
            plan.skipped.append({"item_ref": f"{FONTE}:invalid", "reason": "bad_id"})
            continue
        folder = raw_root / FONTE / decision_id
        decision = read_decision(folder / "decision.json", folder_id=decision_id)
        if isinstance(decision, Rejected):
            plan.skipped.append({"item_ref": ref, "reason": decision.reason})
            continue
        sidecar = _sidecar(folder)
        plan.warnings.extend(f"{ref}: {warning}" for warning in decision.warnings)
        if decision.text is not None:
            plan.rozhodnutia.append(_row(decision, decision.text, "api", sidecar))
            continue
        plan.pdf_only += 1
        if not include_pdf_only:
            plan.skipped.append({"item_ref": ref, "reason": "pdf_only_disabled"})
            continue
        text, source, reason = _pdf_text(folder / "attachment.pdf", ocr_fn)
        if reason is not None:
            plan.skipped.append({"item_ref": ref, "reason": reason})
            continue
        plan.ocr += 1 if source == "ocr" else 0
        plan.rozhodnutia.append(_row(decision, text, source, sidecar))
    if item_meta.get("from") and item_meta.get("to"):
        plan.coverage = {
            "window_from": item_meta["from"],
            "window_to": item_meta["to"],
            "ids_listed": int(index.get("listed", len(index.get("ids", [])))),
            "ids_taken": len(plan.rozhodnutia),
            "pdf_only": plan.pdf_only,
        }
    return plan
