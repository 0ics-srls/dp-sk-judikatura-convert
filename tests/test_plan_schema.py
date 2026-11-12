"""The plan written by convert validates against plan.schema.json (the ingest class ships a byte-identical copy and tests it, P79 schema-sync lesson)."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from dp_sk_judikatura_convert.convert import run_convert

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.unit
def test_a_plan_with_api_pdf_and_skipped_entries_validates(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    for decision_id, body in (("150000", (FIXTURES / "decision-150000.json").read_text(encoding="utf-8")), ("9", "{broken")):
        folder = raw / "nsud" / decision_id
        folder.mkdir(parents=True)
        (folder / "decision.json").write_text(body, encoding="utf-8")
    (raw / "items").mkdir()
    (raw / "items" / "nsud_2026-09.json").write_text(json.dumps({"ids": ["150000", "9"], "listed": 2}), encoding="utf-8")
    item = {"key": "k", "meta": {"kind": "nsud", "itemId": "nsud:2026-09", "from": "2026-09-01", "to": "2026-09-30"}}

    run_convert({"items": [item], "dirIn": str(raw), "dirOut": str(tmp_path / "out")}, lambda *_: None)

    plan = json.loads((tmp_path / "out" / "nsud_2026-09.plan.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "plan.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(plan)
