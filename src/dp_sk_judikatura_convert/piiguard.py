"""Shape guard (P81-10): counts strings shaped like personal data in a decision text. It NEVER blocks and never rewrites: the Court anonymises the decisions
before publication, this only makes a miss visible (``pii_flags`` in the plan, shown by the status Tool and the Screen)."""
from __future__ import annotations

import re
from dataclasses import dataclass

# yymmdd/xxx(x); the month carries +50 for women, the day is 01-31
_BIRTH_NUMBER = re.compile(r"\b\d{2}(?:0[1-9]|1[0-2]|5[1-9]|6[0-2])(?:0[1-9]|[12]\d|3[01])/\d{3,4}\b")
_IBAN = re.compile(r"\bSK\d{2}(?: ?\d{4}){5}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PHONE = re.compile(r"\+421 ?\d{3}(?: ?\d{3}){2}\b")


@dataclass(frozen=True)
class PiiCounts:
    """Number of matches per kind."""

    birth_number: int = 0
    iban: int = 0
    email: int = 0
    phone: int = 0

    @property
    def total(self) -> int:
        return self.birth_number + self.iban + self.email + self.phone


def scan(text: str) -> PiiCounts:
    """Count the matches of each kind in ``text``."""
    return PiiCounts(
        birth_number=len(_BIRTH_NUMBER.findall(text)),
        iban=len(_IBAN.findall(text)),
        email=len(_EMAIL.findall(text)),
        phone=len(_PHONE.findall(text)),
    )
