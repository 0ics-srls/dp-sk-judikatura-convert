"""The ``execute`` action: per item, the grab output (``<dirIn>/items/<item>.json`` index and ``<dirIn>/nsud/<id>/`` decision folders) becomes
``<dirOut>/<item>.plan.json`` (plan v1). A failing item does not stop the others: the run ends with one ``system_error`` listing the failed keys.
Sample filters of the Source (``ids``, ``maxDocs``) were applied by the grab: nothing to trim here; unset (null) settings are absent (P79-30)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dp_sk_judikatura_convert import ocr as ocr_mod
from dp_sk_judikatura_convert import plan as plan_mod

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIG_ERROR = "config_error"
SYSTEM_ERROR = "system_error"
KIND = "nsud"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ConvertError(Exception):
    """A run-level failure carrying one of the protocol error codes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def safe_name(item_id: str) -> str:
    """File name of an item id (identical to the grab class)."""
    return _UNSAFE.sub("_", item_id.replace(" ", "-"))


def _validate_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ConvertError(CONFIG_ERROR, "items must be a non-empty array")
    for entry in items:
        meta = entry.get("meta") if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not entry.get("key") or not isinstance(meta, dict):
            raise ConvertError(CONFIG_ERROR, f"item needs a key and a meta: {entry!r}")
        if meta.get("kind") != KIND or not isinstance(meta.get("itemId"), str) or not meta["itemId"]:
            raise ConvertError(CONFIG_ERROR, f"item {entry['key']}: meta.kind must be '{KIND}' and meta.itemId is required")
    return items


def _convert_item(entry: dict[str, Any], dir_in: Path, dir_out: Path, *, include_pdf_only: bool, ocr_fn: Callable[[Path], str]) -> plan_mod.ItemPlan:
    name = safe_name(entry["meta"]["itemId"])
    index_path = dir_in / "items" / f"{name}.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        msg = f"no readable grab index at {index_path}"
        raise ConvertError(SYSTEM_ERROR, msg) from error
    plan = plan_mod.build_item_plan(dir_in, index, entry["meta"], include_pdf_only=include_pdf_only, ocr_fn=ocr_fn)
    dir_out.mkdir(parents=True, exist_ok=True)
    (dir_out / f"{name}.plan.json").write_text(plan.to_json(), encoding="utf-8")
    return plan


def run_convert(
    raw_params: dict[str, Any], on_progress: Callable[[int, str], None], ocr_fn: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Converts every item; if any failed raises ConvertError(system_error) naming the keys, after the others were written."""
    params = {name: value for name, value in raw_params.items() if value is not None}
    items = _validate_items(params.get("items"))
    dir_in, dir_out = params.get("dirIn"), params.get("dirOut")
    if not isinstance(dir_in, str) or not dir_in or not isinstance(dir_out, str) or not dir_out:
        raise ConvertError(CONFIG_ERROR, "dirIn and dirOut are required")
    include_pdf_only = bool(params.get("includePdfOnly", True))
    reader = ocr_fn or ocr_mod.ocr_pdf
    totals = {"decisions": 0, "pdf": 0, "ocr": 0, "skipped": 0, "warnings": 0, "pii_flags": 0}
    converted: list[dict[str, Any]] = []
    failures: list[str] = []
    for position, entry in enumerate(items):
        try:
            plan = _convert_item(entry, Path(dir_in), Path(dir_out), include_pdf_only=include_pdf_only, ocr_fn=reader)
        except ConvertError as error:
            failures.append(f"{entry['key']} ({error})")
        else:
            totals["decisions"] += len(plan.rozhodnutia)
            totals["pdf"] += sum(1 for row in plan.rozhodnutia if row["text_source"] == "pdf")
            totals["ocr"] += plan.ocr
            totals["skipped"] += len(plan.skipped)
            totals["warnings"] += len(plan.warnings)
            totals["pii_flags"] += sum(row["pii_flags"] for row in plan.rozhodnutia)
            converted.append({"key": entry["key"], "plan": str(Path(dir_out) / f"{safe_name(entry['meta']['itemId'])}.plan.json"), "meta": entry["meta"]})
        on_progress(int((position + 1) * 100 / len(items)), f"{position + 1}/{len(items)} {entry['key']}")
    if failures:
        msg = f"{len(failures)} of {len(items)} items failed: {'; '.join(failures)}"
        raise ConvertError(SYSTEM_ERROR, msg)
    return {"dirOut": dir_out, "converted": converted, "metrics": totals}
