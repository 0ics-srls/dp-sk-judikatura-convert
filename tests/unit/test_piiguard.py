"""Shape guard: counts strings shaped like personal data, never blocks (P81-10)."""
from __future__ import annotations

import pytest

from dp_sk_judikatura_convert.piiguard import PiiCounts, scan


@pytest.mark.unit
def test_should_count_each_kind_once() -> None:
    text = "Rodne cislo 800101/1234 a 855101/1234 (zena), IBAN SK31 1200 0000 1987 4263 7541, jan@example.sk, tel. +421 905 123 456."

    counts = scan(text)

    assert counts == PiiCounts(birth_number=2, iban=1, email=1, phone=1)
    assert counts.total == 5


@pytest.mark.unit
def test_should_count_zero_on_ordinary_case_numbers_dates_and_registry_numbers() -> None:
    text = "Sp. zn. 8Cdo/21/2014, 5Sžo/221/2010, 10Sp/81/2015-17, zo dna 26.01.2017, ICO 35 807 598, DIC 2020123456, suma 14 377,09 eur, cislo spisu 7015201167."

    assert scan(text).total == 0


@pytest.mark.unit
def test_should_not_match_an_impossible_birth_number_month_or_day() -> None:
    assert scan("801301/1234 800132/1234 806301/1234").birth_number == 0


@pytest.mark.unit
def test_should_accept_a_compact_iban_and_a_plain_phone() -> None:
    counts = scan("SK3112000000198742637541 a +421905123456")

    assert counts.iban == 1
    assert counts.phone == 1


@pytest.mark.unit
def test_should_handle_empty_text() -> None:
    assert scan("").total == 0
