# Demo Dataset Report

Generator: `scripts/generate_demo_corpus.py` → `demo_data/multiformat/`
(run `python scripts/generate_demo_corpus.py --upload` to ingest via the API).

The dataset is **self-authored and openly licensed** (synthetic industrial
content). Downloading third-party corpora was not used because this environment
has no outbound package/network access; generating the corpus guarantees a
license-clean, reproducible dataset that still exercises every parser and brain.
All content is centered on the seeded Knowledge Graph entities (pump `P-102A`,
motor `M-330`, valve `VLV-501`, sensors `FT-101`/`TE-202`, failure modes
`FM-BRG-01`/`FM-SEAL-03`, work order `WO-99201`) so GraphRAG, the graph view, and
all five brains light up on it.

## Files and format coverage

| File | Format | Industrial type | Exercises |
|------|--------|-----------------|-----------|
| `SOP-PUMP-ISOLATION.docx` | DOCX | SOP | DocxParser (headings, numbered steps) |
| `MAINTENANCE-LOG.xlsx` | XLSX | maintenance log | XlsxParser (tables) |
| `MAINTENANCE-LOG.csv` | CSV | maintenance log | TextParser → TABLE chunk |
| `WORK-ORDERS.csv` | CSV | work orders | TextParser → TABLE chunk |
| `INSPECTION-P102A.json` | JSON | inspection form | TextParser (flattened keys) |
| `EQUIPMENT-SPEC-P102A.json` | JSON | equipment spec | TextParser |
| `INCIDENT-INC-2026-014.md` | Markdown | incident report | TextParser (heading hierarchy) |
| `VALVE-VLV501-GUIDE.md` | Markdown | valve manual | TextParser |
| `REG-OSHA-1910-147.txt` | TXT | regulation excerpt | TextParser (Compliance brain) |
| `OEM-COMPRESSOR-K410.txt` | TXT | compressor manual | TextParser |
| `ALARM-P102A.eml` | EML | alarm email | EmailParser (headers + body) |
| `SAFETY-BRIEFING-P102A.pptx` | PPTX | safety slides | PptxParser (when python-pptx present) |
| `P102A-RECORDS-BUNDLE.zip` | ZIP | mixed bundle | ZipParser → routes inner md/csv/json |

> The regulation excerpt is titled with an OSHA keyword (`OSHA 1910.147`) so the
> [Compliance brain's](../manual/DEVELOPER_GUIDE.md) regulation heuristic
> recognises it.

## Format support matrix (universal ingestion)

Handled by the parser registry (`domain/document/parser_registry.py`), detection
by extension + content sniff (`domain/document/mime.py`):

- **Native**: PDF, DOCX, XLSX, PPTX
- **Text/structured (stdlib)**: TXT, LOG, Markdown, CSV, TSV, JSON, XML, HTML, YAML
- **Images (OCR when PaddleOCR present)**: PNG, JPG/JPEG, GIF, BMP, TIFF, WEBP
- **Email**: EML (stdlib), MSG (extract-msg optional)
- **Archive**: ZIP (recursively routes entries to leaf parsers; zip-bomb guarded)

Optional dependencies (`python-pptx`, `extract-msg`) degrade gracefully when
absent, so ingestion never fails on a PPTX or MSG upload.
