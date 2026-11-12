"""PDF text layer through pypdfium2 (P81-05 spike: 24 of 24 sampled PDF-only decisions of 2008, 2011 and 2014 carry a real text layer)."""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from dp_sk_judikatura_convert import pdftext
from dp_sk_judikatura_convert.ocr import needs_ocr

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _blank_pdf(path: Path) -> Path:
    document = pdfium.PdfDocument.new()
    document.new_page(595, 842)
    document.save(str(path))
    document.close()
    return path


@pytest.mark.unit
@pytest.mark.parametrize("name", ["decision-textlayer-2014.pdf", "decision-textlayer-2008.pdf"])
def test_should_give_text_with_slovak_diacritics_intact_when_the_pdf_has_a_text_layer(name: str) -> None:
    text = pdftext.extract_text(FIXTURES / name)

    assert not needs_ocr(text)
    assert "Najvyšší súd" in unicodedata.normalize("NFC", text)
    assert "Slovenskej republiky" in text


@pytest.mark.unit
def test_should_count_a_blank_page_as_no_text(tmp_path: Path) -> None:
    text = pdftext.extract_text(_blank_pdf(tmp_path / "blank.pdf"))

    assert len(text) < 200
    assert needs_ocr(text)


@pytest.mark.unit
def test_should_normalise_no_break_spaces_and_soft_hyphens() -> None:
    dirty = "Najvy\u0161\u0161\u00ed" + chr(0xA0) + "s\u00fad" + chr(0x2007) + "SR" + chr(0x202F) + "sk" + chr(0xAD) + "\u00fa\x07\u0161al"
    assert pdftext.clean_text(dirty) == "Najvy\u0161\u0161\u00ed s\u00fad SR sk\u00fa\u0161al"


@pytest.mark.unit
def test_should_clean_whitespace_runs_but_keep_paragraphs() -> None:
    assert pdftext.clean_text("a   b \t\n\n\n\n\nc\r\nd") == "a b\n\nc\nd"


@pytest.mark.unit
def test_should_raise_a_declared_error_when_the_file_is_not_a_pdf(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")

    with pytest.raises(pdftext.PdfUnreadable):
        pdftext.extract_text(broken)


@pytest.mark.unit
def test_should_page_count_match_the_document() -> None:
    assert pdftext.page_count(FIXTURES / "decision-textlayer-2014.pdf") == 2
