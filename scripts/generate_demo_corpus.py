"""Multi-format industrial demo corpus generator (Performance & Ingestion Upgrade,
Part 5).

Generates a realistic, openly-licensed (self-authored) industrial dataset across
every supported format so the universal ingestion pipeline and all five brains
can be demoed end to end. Content is centered on the same entities as the seeded
Knowledge Graph (pump P-102A, motor M-330, valve VLV-501, sensors FT-101/TE-202,
failure modes, work orders) so GraphRAG, the graph, and the brains all light up.

Usage:
    python scripts/generate_demo_corpus.py            # write files
    python scripts/generate_demo_corpus.py --upload   # write + ingest via the API

Output: demo_data/multiformat/  (+ manifest.json)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import zipfile
from email.message import EmailMessage
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo_data" / "multiformat"


def _sop_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("SOP-PUMP-ISOLATION — Centrifugal Pump P-102A Isolation", level=1)
    doc.add_paragraph(
        "Purpose: safely isolate pump P-102A in Refining Unit 03 before maintenance."
    )
    doc.add_heading("Procedure", level=2)
    for step in [
        "Close the suction valve and the discharge valve VLV-501.",
        "Apply lockout-tagout (LOTO) and a personal lock and tag.",
        "Depressurise the pump casing and verify zero energy.",
        "Confirm flow transmitter FT-101 reads zero before opening the pump.",
    ]:
        doc.add_paragraph(step, style="List Number")
    doc.add_heading("References", level=2)
    doc.add_paragraph("OEM Manual P-102A; ASME BPVC Section VIII; Work Order WO-99201.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _maintenance_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "MaintenanceLog"
    ws.append(["work_order", "equipment", "date", "type", "finding", "hours"])
    rows = [
        ["WO-99201", "P-102A", "2026-01-14", "corrective", "Bearing seizure FM-BRG-01 repaired", 6.5],
        ["WO-99188", "M-330", "2026-01-09", "preventive", "Winding insulation resistance test passed", 2.0],
        ["WO-99205", "VLV-501", "2026-02-02", "corrective", "Gasket weep FM-SEAL-03, gasket replaced", 3.0],
        ["WO-99210", "P-102A", "2026-02-20", "preventive", "Bearings lubricated, vibration nominal", 1.5],
    ]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _maintenance_csv() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["work_order", "equipment", "date", "type", "finding", "hours"])
    w.writerow(["WO-99201", "P-102A", "2026-01-14", "corrective", "Bearing seizure FM-BRG-01 repaired", "6.5"])
    w.writerow(["WO-99205", "VLV-501", "2026-02-02", "corrective", "Gasket weep FM-SEAL-03 replaced", "3.0"])
    return buf.getvalue().encode("utf-8")


def _inspection_json() -> bytes:
    data = {
        "form": "INSPECTION-P102A-2026Q1",
        "equipment": "P-102A",
        "inspector": "J. Rao",
        "date": "2026-03-30",
        "checks": [
            {"item": "discharge pressure", "value": "12 bar", "status": "nominal"},
            {"item": "vibration", "value": "2.1 mm/s", "status": "nominal"},
            {"item": "impeller erosion", "value": "none", "status": "pass"},
        ],
        "recommendation": "Continue routine monitoring of bearing temperature TE-202.",
    }
    return json.dumps(data, indent=2).encode("utf-8")


def _work_orders_csv() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "asset", "priority", "status", "description"])
    w.writerow(["WO-99201", "P-102A", "high", "closed", "Repair bearing seizure FM-BRG-01"])
    w.writerow(["WO-99230", "COOLING-LOOP-A", "medium", "open", "Inspect cooling water supply via VLV-501"])
    return buf.getvalue().encode("utf-8")


def _incident_md() -> bytes:
    return (
        "# Incident Report INC-2026-014 — Pump P-102A Bearing Failure\n\n"
        "## Summary\nOn 2026-01-13, pump P-102A tripped on high bearing temperature "
        "(TE-202). Root cause was bearing seizure (FM-BRG-01).\n\n"
        "## Contributing Factors\n- Missed monthly bearing lubrication.\n"
        "- Vibration trend not reviewed.\n\n"
        "## Corrective Actions\nBearing replaced under WO-99201; lubrication interval "
        "added to the preventive schedule; vibration alarm threshold lowered.\n\n"
        "## Lessons Learned\nReview vibration trends weekly; near-miss on adjacent pump "
        "P-102B suggests a fleet-wide lubrication audit.\n"
    ).encode("utf-8")


def _regulation_txt() -> bytes:
    return (
        "OSHA 1910.147 — The Control of Hazardous Energy (Lockout/Tagout)\n\n"
        "Employers shall establish a program of lockout-tagout procedures for the "
        "servicing and maintenance of machines such as pump P-102A where unexpected "
        "energization could cause injury. Each authorized employee shall apply a "
        "personal lock and tag. This regulation is implemented by SOP-PUMP-ISOLATION "
        "and SOP-LOTO-COOLING-A.\n"
    ).encode("utf-8")


def _equipment_spec_json() -> bytes:
    return json.dumps(
        {
            "tag": "P-102A",
            "name": "Centrifugal Pump P-102A",
            "equipment_class": "pump",
            "rated_pressure_bar": 12,
            "rated_flow_m3h": 320,
            "driver": {"tag": "M-330", "rated_power_kw": 75, "voltage": 415},
            "monitored_by": ["FT-101", "TE-202"],
            "failure_modes": ["FM-BRG-01", "FM-SEAL-03"],
        },
        indent=2,
    ).encode("utf-8")


def _compressor_txt() -> bytes:
    return (
        "OEM MANUAL — Reciprocating Compressor K-410\n\n"
        "Rated discharge pressure 35 bar. Interstage cooler served by Cooling Loop A. "
        "Preventive maintenance: replace valve plates every 8000 hours; monitor rod "
        "load and discharge temperature. Common failure mode: valve plate fatigue.\n"
    ).encode("utf-8")


def _valve_md() -> bytes:
    return (
        "# Gate Valve VLV-501 (Velan) — Maintenance Guide\n\n"
        "## Overview\nGate valve VLV-501 is part of Cooling Loop A, serving cooling "
        "water supply.\n\n"
        "## Failure Modes\n- Gasket leakage (FM-SEAL-03): inspect seat annually.\n\n"
        "## Procedure\nIsolate per SOP-LOTO-COOLING-A before servicing.\n"
    ).encode("utf-8")


def _alarm_eml() -> bytes:
    msg = EmailMessage()
    msg["From"] = "control.room@refinery.example"
    msg["To"] = "maintenance.lead@refinery.example"
    msg["Subject"] = "ALARM: P-102A high bearing temperature (TE-202)"
    msg.set_content(
        "Pump P-102A alarmed on high bearing temperature at 07:42. Discharge "
        "pressure holding at 12 bar. Recommend inspecting bearing per FM-BRG-01 "
        "and raising a work order. FT-101 flow nominal.\n"
    )
    return msg.as_bytes()


def _safety_pptx() -> bytes | None:
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except Exception:
        return None
    prs = Presentation()
    layout = prs.slide_layouts[1]
    s1 = prs.slides.add_slide(layout)
    s1.shapes.title.text = "Pump P-102A Safety Briefing"
    s1.placeholders[1].text = "Isolation, LOTO, and bearing failure awareness"
    s2 = prs.slides.add_slide(layout)
    s2.shapes.title.text = "Key Points"
    s2.placeholders[1].text = (
        "Close VLV-501 before service.\nApply LOTO.\nWatch TE-202 bearing temperature.\n"
        "FM-BRG-01 is the top failure mode."
    )
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _hindi_maintenance_txt() -> bytes:
    """Hindi maintenance procedure — exercises language detection, BM25
    same-language retrieval, and answer-in-Hindi generation."""
    return (
        "पंप P-102A रखरखाव प्रक्रिया (Refining Unit 03)\n"
        "\n"
        "1. पंप P-102A का रेटेड डिस्चार्ज प्रेशर 12 bar है।\n"
        "2. तेल परिवर्तन हर 3 महीने (तिमाही) में अनिवार्य है।\n"
        "3. बेयरिंग तापमान 85 डिग्री सेल्सियस से अधिक होने पर पंप तुरंत बंद करें।\n"
        "4. मैकेनिकल सील की जांच हर सप्ताह करें — रिसाव मिलने पर वर्क ऑर्डर खोलें।\n"
        "5. कंपन स्तर 7.1 mm/s RMS से ऊपर होने पर वाइब्रेशन विश्लेषण करवाएं।\n"
        "\n"
        "सुरक्षा: रखरखाव से पहले SOP-PUMP-ISOLATION के अनुसार लॉकआउट-टैगआउट करें।\n"
    ).encode("utf-8")


def _tamil_safety_txt() -> bytes:
    """Tamil safety instruction — second Indic language for cross-language demo."""
    return (
        "வால்வு VLV-501 பாதுகாப்பு அறிவுரைகள் (Refining Unit 03)\n"
        "\n"
        "1. வால்வு VLV-501 இன் இயக்க அழுத்தம் அதிகபட்சம் 16 bar ஆகும்.\n"
        "2. ஆக்சுவேட்டர் டயாபிராம் ஒவ்வொரு 3 ஆண்டுகளுக்கும் மாற்றப்பட வேண்டும்.\n"
        "3. பராமரிப்புக்கு முன் லாக்அவுட்-டேக்அவுட் நடைமுறையை பின்பற்றவும்.\n"
        "4. கசிவு கண்டறியப்பட்டால் உடனடியாக கட்டுப்பாட்டு அறைக்கு தெரிவிக்கவும்.\n"
    ).encode("utf-8")


def _scanned_field_note_png() -> bytes | None:
    """A synthetic 'scanned' field note (printed English + a Hindi line) —
    exercises the OCR ingestion path end to end. Returns None when Pillow or
    the Devanagari-capable font is unavailable."""
    try:
        import io as _io

        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1400, 640), "#f4f0e8")
        d = ImageDraw.Draw(img)
        font_big = ImageFont.truetype("arial.ttf", 52)
        font = ImageFont.truetype("arial.ttf", 40)
        d.text((60, 45), "SCANNED FIELD NOTE - PUMP P-102A", fill="#222", font=font_big)
        d.text((60, 170), "Bearing temperature reached 95 C before trip.", fill="#333", font=font)
        d.text((60, 250), "Seal leakage observed at drive end.", fill="#333", font=font)
        d.text((60, 330), "Recommend oil change and vibration check.", fill="#333", font=font)
        try:
            font_hi = ImageFont.truetype("C:/Windows/Fonts/Nirmala.ttc", 46, index=0)
            d.text((60, 450), "सील बदलने की आवश्यकता है। तेल बदलें।", fill="#333", font=font_hi)
        except Exception:
            pass  # Hindi line is a bonus; the English body is the OCR target
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def build() -> List[Tuple[str, bytes]]:
    files: List[Tuple[str, bytes]] = [
        ("SOP-PUMP-ISOLATION.docx", _sop_docx()),
        ("MAINTENANCE-LOG.xlsx", _maintenance_xlsx()),
        ("MAINTENANCE-LOG.csv", _maintenance_csv()),
        ("INSPECTION-P102A.json", _inspection_json()),
        ("WORK-ORDERS.csv", _work_orders_csv()),
        ("INCIDENT-INC-2026-014.md", _incident_md()),
        ("REG-OSHA-1910-147.txt", _regulation_txt()),
        ("EQUIPMENT-SPEC-P102A.json", _equipment_spec_json()),
        ("OEM-COMPRESSOR-K410.txt", _compressor_txt()),
        ("VALVE-VLV501-GUIDE.md", _valve_md()),
        ("ALARM-P102A.eml", _alarm_eml()),
    ]
    pptx = _safety_pptx()
    if pptx is not None:
        files.append(("SAFETY-BRIEFING-P102A.pptx", pptx))
    # Multilingual intelligence (Performance & Intelligence Upgrade)
    files.append(("HINDI-MAINT-P102A.txt", _hindi_maintenance_txt()))
    files.append(("TAMIL-SAFETY-VLV501.txt", _tamil_safety_txt()))
    # OCR ingestion path — synthetic scanned field note
    scan = _scanned_field_note_png()
    if scan is not None:
        files.append(("SCANNED-FIELD-NOTE-P102A.png", scan))
    # a mixed archive to exercise the ZIP parser
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("readme.md", "# P-102A Records Bundle\nWork orders and inspection.")
        zf.writestr("work-orders.csv", _work_orders_csv().decode("utf-8"))
        zf.writestr("inspection.json", _inspection_json().decode("utf-8"))
    files.append(("P102A-RECORDS-BUNDLE.zip", zbuf.getvalue()))
    return files


def upload(files: List[Tuple[str, bytes]]) -> None:
    import httpx

    base = os.environ.get("DEMO_API_BASE", "http://127.0.0.1:8000")
    user = os.environ.get("DEMO_USER", "ratish01@industrialbrain.local")
    pw = os.environ.get("DEMO_PASSWORD", "Ratish*966")
    with httpx.Client(base_url=base, timeout=60.0) as c:
        tok = c.post("/api/v1/auth/login", data={"username": user, "password": pw}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        for name, data in files:
            r = c.post("/api/v1/documents/", headers=h, files={"file": (name, data, "application/octet-stream")})
            print(f"  upload {name}: {r.status_code}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true", help="ingest via the API after writing")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    files = build()
    manifest = []
    for name, data in files:
        (OUT / name).write_bytes(data)
        manifest.append({"file": name, "bytes": len(data)})
    (OUT / "manifest.json").write_text(json.dumps({"files": manifest}, indent=2), encoding="utf-8")
    print(f"Wrote {len(files)} demo files to {OUT}")
    for m in manifest:
        print(f"  {m['file']} ({m['bytes']} B)")
    if args.upload:
        print("Uploading to the API…")
        upload(files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
