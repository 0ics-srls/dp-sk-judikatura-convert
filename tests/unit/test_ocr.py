"""Local OCR (tesseract CLI, slk, 200 dpi). Tests marked ``ocr`` need the binary and run inside Dockerfile.test."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pytest

from dp_sk_judikatura_convert import ocr

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _blank_pdf(path: Path, pages: int = 1) -> Path:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842)
    document.save(str(path))
    document.close()
    return path


def _scan_of(source: Path, target: Path) -> Path:
    """An image-only PDF (no text layer) made from the first page of a real decision: what a scanned decision looks like."""
    document = pdfium.PdfDocument(str(source))
    try:
        page = document[0]
        image = page.render(scale=200 / 72).to_pil().convert("L")
        page.close()
    finally:
        document.close()
    image.save(str(target), "PDF", resolution=200)
    return target


@pytest.mark.unit
def test_should_apply_the_200_character_threshold() -> None:
    assert ocr.needs_ocr("")
    assert ocr.needs_ocr("   5  ")
    assert ocr.needs_ocr("x" * 199)
    assert not ocr.needs_ocr("x" * 200)
    assert ocr.needs_ocr("x" * 250, threshold=300)


@pytest.mark.unit
def test_should_call_tesseract_with_an_argument_list_in_slovak_and_never_through_a_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    def fake_run(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="Najvyšší súd rozhodol", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    text = ocr.ocr_pdf(_blank_pdf(tmp_path / "one.pdf"))

    assert text == "Najvyšší súd rozhodol"
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert isinstance(argv, list)
    assert argv[0] == "tesseract"
    assert argv[argv.index("-l") + 1] == "slk"
    assert not kwargs.get("shell", False)
    assert kwargs["timeout"] == 120


@pytest.mark.unit
def test_should_join_pages_with_a_form_feed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    outputs = iter(["strana jedna", "strana dva"])

    def fake_run(args: Any, **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=next(outputs), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ocr.ocr_pdf(_blank_pdf(tmp_path / "two.pdf", pages=2)) == "strana jedna\x0cstrana dva"


@pytest.mark.unit
def test_should_raise_ocr_empty_when_tesseract_reads_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(args: Any, **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=" \n ", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ocr.OcrEmpty):
        ocr.ocr_pdf(_blank_pdf(tmp_path / "blank.pdf"))


@pytest.mark.unit
def test_should_raise_a_clear_error_when_the_binary_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("tesseract")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ocr.OcrUnavailable, match="tesseract"):
        ocr.ocr_pdf(_blank_pdf(tmp_path / "x.pdf"))


@pytest.mark.unit
def test_should_raise_a_declared_error_when_tesseract_times_out_or_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def timeout(args: Any, **_: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, 120)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ocr.OcrFailed):
        ocr.ocr_pdf(_blank_pdf(tmp_path / "t.pdf"))

    def failing(args: Any, **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", failing)
    with pytest.raises(ocr.OcrFailed):
        ocr.ocr_pdf(_blank_pdf(tmp_path / "f.pdf"))


@pytest.mark.ocr
def test_should_read_a_scanned_decision_with_the_real_binary(tmp_path: Path) -> None:
    scan = _scan_of(FIXTURES / "decision-textlayer-2014.pdf", tmp_path / "scan.pdf")

    text = ocr.ocr_pdf(scan)

    assert len(text) > 200
    lowered = text.lower()
    # distinctive words of the page, typed by hand
    for word in ("slovenskej", "republiky", "uznesenie"):
        assert word in lowered, word


@pytest.mark.ocr
def test_should_declare_a_blank_page_as_ocr_empty_with_the_real_binary(tmp_path: Path) -> None:
    with pytest.raises(ocr.OcrEmpty):
        ocr.ocr_pdf(_blank_pdf(tmp_path / "blank.pdf"))
