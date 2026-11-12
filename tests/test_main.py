"""convert: the `execute` action end to end (item index of the grab, decision folders, plan file, metrics) and the Proc-protocol loop."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pytest

import main
from dp_sk_judikatura_convert import ocr
from dp_sk_judikatura_convert.convert import CONFIG_ERROR, ConvertError, run_convert

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ITEM = {"key": "nsud:2026-09|1", "meta": {"kind": "nsud", "itemId": "nsud:2026-09", "version": "1", "from": "2026-09-01", "to": "2026-09-30"}}


def fake_ocr(_path: Path) -> str:
    return "Najvyšší súd Slovenskej republiky rozhodol o dovolaní. " * 10


def _blank_pdf(path: Path) -> None:
    document = pdfium.PdfDocument.new()
    document.new_page(595, 842)
    document.save(str(path))
    document.close()


def _decision(root: Path, decision_id: str, body: str, pdf: Path | None = None, *, pdf_blank: bool = False) -> None:
    folder = root / "nsud" / decision_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "decision.json").write_text(body, encoding="utf-8")
    sidecar: dict[str, Any] = {"id": decision_id, "version": "1", "pdfUrl": None, "subor": None, "pageUrl": None}
    if pdf is not None:
        shutil.copy(pdf, folder / "attachment.pdf")
        sidecar["pdfUrl"] = f"https://www.nsud.sk/data/att/x/{decision_id}.pdf"
    if pdf_blank:
        _blank_pdf(folder / "attachment.pdf")
        sidecar["pdfUrl"] = f"https://www.nsud.sk/data/att/x/{decision_id}.pdf"
    (folder / "fetch.json").write_text(json.dumps(sidecar), encoding="utf-8")


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    base = tmp_path / "raw"
    _decision(base, "150000", (FIXTURES / "decision-150000.json").read_text(encoding="utf-8"))
    _decision(base, "177749", (FIXTURES / "decision-177749.json").read_text(encoding="utf-8"), pdf=FIXTURES / "decision-textlayer-2008.pdf")
    _decision(base, "5", "{not json")
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 3, "ids": ["150000", "177749", "5"]}), encoding="utf-8")
    return base


def params(raw: Path, tmp_path: Path, **extra: Any) -> dict[str, Any]:
    return {"items": [ITEM], "dirIn": str(raw), "dirOut": str(tmp_path / "plan"), **extra}


def read_plan(tmp_path: Path, folder: str = "plan") -> dict[str, Any]:
    plan: dict[str, Any] = json.loads((tmp_path / folder / "nsud_2026-09.plan.json").read_text(encoding="utf-8"))
    return plan


@pytest.mark.unit
def test_should_write_one_plan_with_rows_skipped_and_coverage(raw: Path, tmp_path: Path) -> None:
    result = run_convert(params(raw, tmp_path), lambda *_: None, ocr_fn=fake_ocr)

    plan = read_plan(tmp_path)
    assert plan["planVersion"] == 1
    rows = {row["source_id"]: row for row in plan["rozhodnutia"]}
    assert set(rows) == {"150000", "177749"}
    assert rows["150000"]["text_source"] == "api"
    assert rows["150000"]["court"] == "NSSR"
    assert rows["150000"]["ecli"] == "ECLI:SK:NSSR:2017:7015201167.1"
    assert rows["150000"]["datum_rozhodnutia"] == "2017-01-26"
    assert rows["150000"]["fonte"] == "nsud"
    assert rows["150000"]["pii_flags"] == 0
    assert rows["177749"]["text_source"] == "pdf"
    assert rows["177749"]["ecli"] is None
    assert "Najvyšší súd" in rows["177749"]["text_raw"]
    assert rows["177749"]["pdf_url"] == "https://www.nsud.sk/data/att/x/177749.pdf"
    assert rows["177749"]["source_url"] == "https://www.nsud.sk/data/att/x/177749.pdf"
    assert plan["skipped"] == [{"item_ref": "nsud:5", "reason": "parse_error"}]
    assert plan["coverage"] == {"window_from": "2026-09-01", "window_to": "2026-09-30", "ids_listed": 3, "ids_taken": 2, "pdf_only": 1}
    assert result["metrics"] == {"decisions": 2, "pdf": 1, "ocr": 0, "skipped": 1, "warnings": 0, "pii_flags": 0}
    assert result["converted"][0]["key"] == ITEM["key"]


@pytest.mark.unit
def test_should_skip_pdf_only_decisions_when_include_pdf_only_is_false(raw: Path, tmp_path: Path) -> None:
    run_convert(params(raw, tmp_path, includePdfOnly=False), lambda *_: None, ocr_fn=fake_ocr)

    plan = read_plan(tmp_path)
    assert [row["source_id"] for row in plan["rozhodnutia"]] == ["150000"]
    assert {"item_ref": "nsud:177749", "reason": "pdf_only_disabled"} in plan["skipped"]
    assert plan["coverage"]["pdf_only"] == 1


@pytest.mark.unit
def test_should_treat_null_settings_as_absent(raw: Path, tmp_path: Path) -> None:
    nulls = {"includePdfOnly": None, "maxDocs": None, "ids": None, "dryRun": None, "annoFrom": None, "annoTo": None, "baseUrl": None, "verifyTls": None, "refreshToken": None}

    result = run_convert(params(raw, tmp_path, **nulls), lambda *_: None, ocr_fn=fake_ocr)

    assert result["metrics"]["decisions"] == 2


@pytest.mark.unit
def test_plan_is_byte_identical_when_run_twice(raw: Path, tmp_path: Path) -> None:
    run_convert(params(raw, tmp_path), lambda *_: None, ocr_fn=fake_ocr)
    first = (tmp_path / "plan" / "nsud_2026-09.plan.json").read_bytes()
    run_convert({**params(raw, tmp_path), "dirOut": str(tmp_path / "second")}, lambda *_: None, ocr_fn=fake_ocr)

    assert (tmp_path / "second" / "nsud_2026-09.plan.json").read_bytes() == first


@pytest.mark.unit
def test_should_fall_back_to_ocr_when_the_pdf_has_no_text_layer(tmp_path: Path) -> None:
    base = tmp_path / "raw"
    _decision(base, "177749", (FIXTURES / "decision-177749.json").read_text(encoding="utf-8"), pdf_blank=True)
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 1, "ids": ["177749"]}), encoding="utf-8")

    result = run_convert(params(base, tmp_path), lambda *_: None, ocr_fn=fake_ocr)

    plan = read_plan(tmp_path)
    assert plan["rozhodnutia"][0]["text_source"] == "ocr"
    assert result["metrics"]["ocr"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(("error", "reason"), [(ocr.OcrEmpty("nothing"), "ocr_empty"), (ocr.OcrUnavailable("tesseract"), "ocr_unavailable"), (ocr.OcrFailed("timeout"), "ocr_failed")])
def test_should_declare_a_decision_skipped_when_ocr_cannot_read_it(tmp_path: Path, error: Exception, reason: str) -> None:
    base = tmp_path / "raw"
    _decision(base, "177749", (FIXTURES / "decision-177749.json").read_text(encoding="utf-8"), pdf_blank=True)
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 1, "ids": ["177749"]}), encoding="utf-8")

    def failing(_path: Path) -> str:
        raise error

    run_convert(params(base, tmp_path), lambda *_: None, ocr_fn=failing)

    plan = read_plan(tmp_path)
    assert plan["rozhodnutia"] == []
    assert plan["skipped"] == [{"item_ref": "nsud:177749", "reason": reason}]


@pytest.mark.unit
def test_should_skip_a_pdf_only_decision_whose_attachment_was_not_grabbed(tmp_path: Path) -> None:
    base = tmp_path / "raw"
    _decision(base, "177749", (FIXTURES / "decision-177749.json").read_text(encoding="utf-8"))
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 1, "ids": ["177749"]}), encoding="utf-8")

    run_convert(params(base, tmp_path), lambda *_: None, ocr_fn=fake_ocr)

    assert read_plan(tmp_path)["skipped"] == [{"item_ref": "nsud:177749", "reason": "pdf_missing"}]


@pytest.mark.unit
def test_should_count_shape_hits_into_pii_flags_without_blocking(tmp_path: Path) -> None:
    base = tmp_path / "raw"
    body = json.dumps({"ID": "", "cislo": "1Cdo/1/2020", "obsah": "Zalobca, rodne cislo 800101/1234, e-mail jan@example.sk."})
    _decision(base, "42", body)
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 1, "ids": ["42"]}), encoding="utf-8")

    result = run_convert(params(base, tmp_path), lambda *_: None, ocr_fn=fake_ocr)

    assert read_plan(tmp_path)["rozhodnutia"][0]["pii_flags"] == 2
    assert result["metrics"]["pii_flags"] == 2


@pytest.mark.unit
def test_should_flag_an_odd_ecli_as_a_warning(tmp_path: Path) -> None:
    base = tmp_path / "raw"
    _decision(base, "43", json.dumps({"ID": "", "cislo": "1Cdo/1/2020", "ecli": "ECLI:XX:odd", "obsah": "text"}))
    (base / "items").mkdir()
    (base / "items" / "nsud_2026-09.json").write_text(json.dumps({"itemId": "nsud:2026-09", "version": "1", "listed": 1, "ids": ["43"]}), encoding="utf-8")

    result = run_convert(params(base, tmp_path), lambda *_: None, ocr_fn=fake_ocr)

    assert read_plan(tmp_path)["warnings"] == ["nsud:43: odd_ecli"]
    assert result["metrics"]["warnings"] == 1


@pytest.mark.unit
def test_should_reject_missing_directories_and_bad_items(raw: Path, tmp_path: Path) -> None:
    with pytest.raises(ConvertError) as no_items:
        run_convert({"dirIn": str(raw), "dirOut": str(tmp_path)}, lambda *_: None)
    assert no_items.value.code == CONFIG_ERROR
    with pytest.raises(ConvertError) as no_dirs:
        run_convert({"items": [ITEM]}, lambda *_: None)
    assert no_dirs.value.code == CONFIG_ERROR


@pytest.mark.unit
def test_should_drive_the_proc_protocol_loop(raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "ocr_pdf", lambda *_a, **_k: fake_ocr(Path()))
    request = {"_action": "execute", "_meta": {"executionId": "e1"}, **params(raw, tmp_path)}
    stdin = io.StringIO("\n".join([json.dumps(request), json.dumps({"_action": "bogus", "_meta": {"executionId": "e1"}}), "not json", json.dumps({"_action": "terminate", "_meta": {"executionId": "e1"}})]) + "\n")
    stdout = io.StringIO()

    code = main.main(stdin, stdout)

    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert code == 1
    assert [e["type"] for e in events].count("result") == 1
    assert [e["code"] for e in events if e["type"] == "error"] == [CONFIG_ERROR, CONFIG_ERROR]
