from __future__ import annotations

import pytest

from dp_sk_judikatura_convert.court import court_of, kolegium_name


def test_ecli_court_code_wins_over_the_header_line() -> None:
    assert court_of("ECLI:SK:NSSSR:2022:1234.1", "Súd:\tNajvyšší súd SR\nSpisová značka: 1") == "NSSSR"
    assert court_of("ECLI:SK:NSSR:2017:7015201167.1", "Súd:\tNajvyšší správny súd SR") == "NSSR"


def test_header_line_is_used_when_the_ecli_is_blank() -> None:
    assert court_of(None, "Súd:\tNajvyšší správny súd Slovenskej republiky\nSpisová značka: 1") == "NSSSR"
    assert court_of("", "Súd:\tNajvyšší súd SR\nSpisová značka: 1") == "NSSR"


def test_header_line_without_diacritics_works_too() -> None:
    assert court_of(None, "Sud:\tNajvyssi spravny sud SR") == "NSSSR"


def test_default_is_nssr() -> None:
    assert court_of(None, None) == "NSSR"
    assert court_of("ECLI:SK:KSBA:2020:1.1", "Súd: Krajský súd Bratislava") == "NSSR"


@pytest.mark.parametrize(("code", "name"), [("1", "Občianskoprávne"), ("2", "Obchodnoprávne"), ("3", "Správne"), ("4", "Trestnoprávne"), ("9", None), (None, None)])
def test_kolegium_name_maps_the_code(code: str | None, name: str | None) -> None:
    assert kolegium_name(code) == name
