"""Port of the golden cases of the legacy SkDecisionReaderTests plus the new PDF-only rule (P81-05)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from dp_sk_judikatura_convert.reader import Decision, Rejected, read_decision

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

RAW_EMPTY_ID = (
    '{"ID":"","cislo":"3Cdo/29/2025","senat":"3","ecli":"ECLI:SK:NSSR:2026:6123336056.1",'
    '"datum":"2026-03-25","kolegium":"1","merito":"14 377,09 eur","sudca":"Mgr. Renáta Gavalcová","obsah":"Najvyšší súd SR rozhodol …"}'
)
RAW_ARRAY_WRAPPED = (
    '[{"ID":12345,"Cislo":"8Cdo/27/2025","Senat":"8","Ecli":"ECLI:SK:NSSR:2026:12345","Datum":"2026-05-13","Kolegium":"1",'
    '"Merito":"náhrada škody","Sudca":"Mgr. Miroslav Šepták","Obsah":"Najvyšší súd Slovenskej republiky rozhodol …"}]'
)
LEGACY_RESHAPED = (
    '{"id":"12345","court":"NSSR","cislo":"8Cdo/27/2025","senat":"8","ecli":"ECLI:SK:NSSR:2026:12345","datum":"2026-05-13","kolegium":"1",'
    '"merito":"náhrada škody","sudca":"Mgr. Miroslav Šepták","obsah":"Najvyšší súd Slovenskej republiky rozhodol …","fetched":"2026-06-01T00:00:00Z"}'
)


def write(tmp_path: Path, body: str, folder: str = "nsud/246004") -> Path:
    target = tmp_path / folder
    target.mkdir(parents=True, exist_ok=True)
    path = target / "decision.json"
    path.write_text(body, encoding="utf-8")
    return path


def as_decision(result: Decision | Rejected) -> Decision:
    assert isinstance(result, Decision), result
    return result


def test_array_wrapped_body_parses_court_defaults_nssr_id_from_numeric_id(tmp_path: Path) -> None:
    decision = as_decision(read_decision(write(tmp_path, RAW_ARRAY_WRAPPED, "nsud/999")))

    assert decision.court == "NSSR"
    assert decision.source_id == "12345"
    assert decision.cislo == "8Cdo/27/2025"


def test_raw_empty_id_takes_the_id_from_the_folder(tmp_path: Path) -> None:
    decision = as_decision(read_decision(write(tmp_path, RAW_EMPTY_ID)))

    assert decision.source_id == "246004"
    assert decision.cislo == "3Cdo/29/2025"
    assert decision.datum == date(2026, 3, 25)
    assert decision.kolegium == "1"
    assert decision.kolegium_nazov == "Občianskoprávne"


def test_single_object_not_wrapped_parses(tmp_path: Path) -> None:
    single = RAW_ARRAY_WRAPPED.strip()[1:-1]

    assert isinstance(read_decision(write(tmp_path, single)), Decision)


def test_legacy_reshaped_body_still_parses_and_matches_the_raw_id(tmp_path: Path) -> None:
    legacy = as_decision(read_decision(write(tmp_path, LEGACY_RESHAPED, "nsud/1")))
    raw = as_decision(read_decision(write(tmp_path, RAW_ARRAY_WRAPPED, "nsud/2")))

    assert legacy.source_id == raw.source_id == "12345"
    assert legacy.court == "NSSR"


def test_empty_array_is_rejected(tmp_path: Path) -> None:
    assert read_decision(write(tmp_path, "[]")) == Rejected("parse_error")


def test_broken_json_is_rejected(tmp_path: Path) -> None:
    assert read_decision(write(tmp_path, "{not json")) == Rejected("parse_error")


def test_missing_cislo_is_rejected(tmp_path: Path) -> None:
    assert read_decision(write(tmp_path, '{"id":"1","obsah":"text"}')) == Rejected("parse_error")


def test_no_text_and_no_pdf_is_rejected_as_no_text(tmp_path: Path) -> None:
    assert read_decision(write(tmp_path, '{"id":"1","cislo":"X","obsah":""}')) == Rejected("no_text")
    assert read_decision(write(tmp_path, '{"id":"1","cislo":"X"}')) == Rejected("no_text")


def test_blank_senat_ecli_sudca_become_none_and_bad_date_becomes_none(tmp_path: Path) -> None:
    body = '{"ID":"","cislo":"1Cdo/1/2020","senat":" ","ecli":"","datum":"31.31.2020","sudca":"  ","obsah":"text"}'

    decision = as_decision(read_decision(write(tmp_path, body)))

    assert decision.senat is None
    assert decision.ecli is None
    assert decision.sudca is None
    assert decision.datum is None
    assert decision.merito == ""
    assert decision.kolegium is None
    assert decision.kolegium_nazov is None


def test_real_body_of_id_150000_gives_court_from_the_ecli_and_the_full_text() -> None:
    decision = as_decision(read_decision(FIXTURES / "decision-150000.json", folder_id="150000"))

    assert decision.source_id == "150000"
    assert decision.court == "NSSR"
    assert decision.kolegium == "3"
    assert decision.kolegium_nazov == "Správne"
    assert decision.ecli == "ECLI:SK:NSSR:2017:7015201167.1"
    assert decision.text is not None
    assert len(decision.text) == 4302
    assert decision.datum == date(2017, 1, 26)
    assert decision.pdf is not None
    assert decision.pdf.endswith(".pdf")


def test_pdf_only_body_of_id_177749_is_not_a_rejection() -> None:
    decision = as_decision(read_decision(FIXTURES / "decision-177749.json", folder_id="177749"))

    assert decision.text is None
    assert decision.pdf == "eec/363149.0d1260.pdf"
    assert decision.ecli is None
    assert decision.sudca is None
    assert decision.datum == date(2011, 5, 19)
    assert decision.cislo == "5Sžo/221/2010"


@pytest.mark.parametrize("folder", ["../../x", "..", "12a", "1 2", ""])
def test_a_folder_id_that_is_not_digits_is_rejected(tmp_path: Path, folder: str) -> None:
    path = tmp_path / "decision.json"
    path.write_text('{"ID":"","cislo":"X","obsah":"text"}', encoding="utf-8")

    assert read_decision(path, folder_id=folder) == Rejected("bad_id")


def test_a_body_id_that_is_a_path_traversal_is_rejected(tmp_path: Path) -> None:
    body = json.dumps({"ID": "../../x", "cislo": "X", "obsah": "text"})

    assert read_decision(write(tmp_path, body)) == Rejected("bad_id")


def test_an_odd_ecli_is_kept_and_flagged(tmp_path: Path) -> None:
    decision = as_decision(read_decision(write(tmp_path, '{"ID":"","cislo":"X","ecli":"ECLI:XX:odd","obsah":"text"}')))

    assert decision.ecli == "ECLI:XX:odd"
    assert decision.warnings == ("odd_ecli",)
