# dp-sk-judikatura-convert

Proc-protocol class (Python 3.12) of the `sk-judikatura` package: turns the grab output of the Supreme Court (NS SR) OpenData decisions into one
`<item>.plan.json` per item (plan v1, `plan.schema.json`).

- `reader.py` port of the legacy `SkDecisionReader` (object or array-wrapped body, case-insensitive keys, id from `ID` or the `nsud/<id>/` folder, digits only).
  New: a decision with an empty `obsah` but a `subor` (PDF attachment) is a PDF-only decision, not a rejection (P81-05).
- `court.py` court from the ECLI court code, else the `Sud:` header line, else NSSR; chamber names.
- `pdftext.py` text layer by pypdfium2 (spike P81-05: 24 of 24 sampled PDF-only decisions of 2008, 2011 and 2014 have a real text layer); `ocr.py` local tesseract
  (`slk`, 200 dpi, argument list, no shell) as the fallback; an OCR that reads nothing puts the decision into `skipped`.
- `piiguard.py` shape guard: counts birth-number, IBAN, e-mail and phone shaped strings into `pii_flags`; it never blocks.
- Settings `includePdfOnly`, `maxDocs`, `ids`, `dryRun` and any undeclared Source key arrive as null and are treated as absent.

Tests: `.venv/Scripts/python -m pytest -m "not integration" tests`; the `ocr` marker needs tesseract and runs in the test image.
`docker build -f Dockerfile.test .` (installs `tesseract-ocr tesseract-ocr-slk`): 66 passed including the real OCR of a scanned decision page. Image size 545 MB,
first build about 30 s. `tests/test_collectable.py` guards the phase 78/79 defect (module-level `parents[n]`).
