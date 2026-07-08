"""Demo dataset loader (M19) — `make demo-data`.

Loads a self-contained industrial demo dataset so the platform is immediately
demoable:

  --graph  (default on): seed the Neo4j knowledge graph with a realistic
           Refining-Unit-03 subgraph (assets, equipment, sensors, failure
           modes, procedures, documents, regulation) using idempotent MERGEs.
           This powers the M19 Knowledge Graph visualizer out of the box.

  --docs   generate 10 industrial demo PDFs (2 OEM manuals, 2 SOPs, 2 inspection
           reports, 2 P&ID descriptions, 1 regulatory excerpt, 1 maintenance
           log) into ``demo_data/`` using PyMuPDF (already a dependency).

  --upload upload the generated PDFs to the running backend's ingestion API so
           they flow through the M2->M3->M4->M7 pipeline. Requires the backend
           (and Celery worker) to be up and DEMO_USER/DEMO_PASSWORD credentials.

Usage:
    python scripts/load_demo_data.py                 # graph + docs
    python scripts/load_demo_data.py --graph-only
    python scripts/load_demo_data.py --docs --upload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.infrastructure.config.settings import settings  # noqa: E402

_DEMO_DIR = _REPO_ROOT / "demo_data"

# --- Knowledge-graph seed: (tag, Label, {props}) -------------------------------
_NODES: List[Tuple[str, str, dict]] = [
    ("UNIT-03", "Asset", {"name": "Refining Unit 03", "asset_class": "process_unit"}),
    ("COOLING-LOOP-A", "Asset", {"name": "Cooling Loop A", "asset_class": "utility"}),
    (
        "P-102A",
        "Equipment",
        {
            "name": "Centrifugal Pump P-102A",
            "equipment_class": "pump",
            "rated_pressure_bar": 12,
        },
    ),
    (
        "M-330",
        "Equipment",
        {"name": "Motor M-330", "equipment_class": "motor", "rated_power_kw": 75},
    ),
    (
        "VLV-501",
        "Equipment",
        {
            "name": "Gate Valve VLV-501",
            "equipment_class": "valve",
            "manufacturer": "Velan",
        },
    ),
    (
        "FT-101",
        "Sensor",
        {"name": "Flow Transmitter FT-101", "measurement_type": "flow", "unit": "m3/h"},
    ),
    (
        "TE-202",
        "Sensor",
        {"name": "Thermocouple TE-202", "measurement_type": "temperature", "unit": "C"},
    ),
    (
        "FM-BRG-01",
        "FailureMode",
        {
            "failure_code": "FM-BRG-01",
            "description": "Bearing seizure",
            "severity": "HIGH",
        },
    ),
    (
        "FM-SEAL-03",
        "FailureMode",
        {
            "failure_code": "FM-SEAL-03",
            "description": "Gasket leakage",
            "severity": "MAJOR",
        },
    ),
    (
        "FM-MOT-02",
        "FailureMode",
        {"failure_code": "FM-MOT-02", "description": "Winding insulation breakdown"},
    ),
    (
        "SOP-PUMP-ISOLATION",
        "Procedure",
        {"title": "Pump Isolation SOP", "procedure_type": "isolation"},
    ),
    (
        "SOP-LOTO-COOLING-A",
        "Procedure",
        {"title": "LOTO Cooling Loop A", "procedure_type": "loto"},
    ),
    (
        "OEM-P102A-MANUAL",
        "Document",
        {"title": "P-102A OEM Manual", "document_type": "oem_manual"},
    ),
    (
        "REG-ASME-BPVC",
        "Regulation",
        {"title": "ASME BPVC Section VIII", "issuing_body": "ASME"},
    ),
    (
        "WO-99201",
        "Maintenance",
        {"work_order_id": "WO-99201", "maintenance_type": "corrective"},
    ),
]

# (source_tag, RELATION_TYPE, target_tag) — matches the ontology allowed edges.
_RELATIONS: List[Tuple[str, str, str]] = [
    ("FT-101", "MONITORS", "P-102A"),
    ("TE-202", "MONITORS", "P-102A"),
    ("P-102A", "IS_PART_OF", "UNIT-03"),
    ("M-330", "IS_PART_OF", "UNIT-03"),
    ("VLV-501", "IS_PART_OF", "COOLING-LOOP-A"),
    ("COOLING-LOOP-A", "IS_PART_OF", "UNIT-03"),
    ("P-102A", "EXHIBITS", "FM-BRG-01"),
    ("VLV-501", "EXHIBITS", "FM-SEAL-03"),
    ("M-330", "EXHIBITS", "FM-MOT-02"),
    ("P-102A", "REQUIRES", "SOP-PUMP-ISOLATION"),
    ("COOLING-LOOP-A", "REQUIRES", "SOP-LOTO-COOLING-A"),
    ("OEM-P102A-MANUAL", "REFERENCES", "P-102A"),
    ("OEM-P102A-MANUAL", "REFERENCES", "SOP-PUMP-ISOLATION"),
    ("REG-ASME-BPVC", "REFERENCES", "SOP-PUMP-ISOLATION"),
    ("WO-99201", "PERFORMED_BY", "P-102A"),
]

# --- Demo document set (10 PDFs) ----------------------------------------------
# (filename, title, [paragraphs]) — the facts mirror datasets/golden_qa.json.
_DOCS: List[Tuple[str, str, List[str]]] = [
    (
        "OEM-P102A-MANUAL.pdf",
        "OEM Manual — Centrifugal Pump P-102A",
        [
            "Rated discharge pressure: 12 bar. Rated flow: 320 m3/h.",
            "Mechanical seal replacement: isolate and drain the pump, remove the coupling guard and coupling, remove the seal gland, extract the worn seal, install the new seal, and reassemble to torque spec.",
            "Preventive maintenance: lubricate bearings monthly.",
        ],
    ),
    (
        "OEM-M330-MANUAL.pdf",
        "OEM Manual — Motor M-330",
        [
            "Motor M-330 is rated at 75 kW, 415 V, 3-phase.",
            "Winding insulation breakdown (FM-MOT-02) is detected by insulation resistance testing.",
        ],
    ),
    (
        "SOP-PUMP-ISOLATION.pdf",
        "SOP — Pump P-102A Isolation",
        [
            "Close the suction and discharge valves, apply lockout-tagout, and depressurise the casing before opening the pump.",
        ],
    ),
    (
        "SOP-LOTO-COOLING-A.pdf",
        "SOP — Lockout/Tagout Cooling Loop A",
        [
            "Stop the pump, open the electrical isolator, apply a personal lock and tag, and verify zero energy before work.",
        ],
    ),
    (
        "INSPECTION-P102A-2026Q1.pdf",
        "Inspection Report — P-102A 2026 Q1",
        [
            "Vibration analysis nominal. Discharge pressure stable at 12 bar. No impeller erosion detected.",
        ],
    ),
    (
        "INSPECTION-VLV501-2026Q1.pdf",
        "Inspection Report — VLV-501 2026 Q1",
        [
            "Gate valve VLV-501 (Velan) seat inspection: minor gasket weep consistent with FM-SEAL-03. Recommend gasket replacement.",
        ],
    ),
    (
        "PID-UNIT03.pdf",
        "P&ID Description — Refining Unit 03",
        [
            "Pump P-102A is monitored by flow transmitter FT-101 (flow) and thermocouple TE-202 (bearing temperature).",
            "Gate valve VLV-501 is part of Cooling Loop A, serving the cooling water supply process.",
        ],
    ),
    (
        "PID-COOLING-A.pdf",
        "P&ID Description — Cooling Loop A",
        [
            "Cooling Loop A supplies cooling water to Refining Unit 03 via gate valve VLV-501.",
        ],
    ),
    (
        "REG-ASME-BPVC.pdf",
        "Regulatory Excerpt — ASME BPVC Section VIII",
        [
            "ASME BPVC Section VIII governs pressure relief testing, implemented by the annual relief-valve test procedure.",
        ],
    ),
    (
        "CMMS-WORKORDERS.pdf",
        "Maintenance Log — CMMS Work Orders",
        [
            "Work order WO-99201 references bearing seizure repair (FM-BRG-01) on pump P-102A.",
        ],
    ),
]


def seed_graph() -> None:
    from neo4j import GraphDatabase

    uri = f"bolt://{settings.NEO4J_HOST}:{settings.NEO4J_BOLT_PORT}"
    driver = GraphDatabase.driver(
        uri, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    try:
        with driver.session() as session:
            for tag, label, props in _NODES:
                session.run(
                    f"MERGE (n:{label} {{tag_number: $tag}}) SET n += $props",
                    tag=tag,
                    props={"tag_number": tag, **props},
                )
            for src, rel, tgt in _RELATIONS:
                session.run(
                    f"MATCH (a {{tag_number: $src}}), (b {{tag_number: $tgt}}) "
                    f"MERGE (a)-[:{rel}]->(b)",
                    src=src,
                    tgt=tgt,
                )
        print(
            f"Seeded knowledge graph: {len(_NODES)} nodes, "
            f"{len(_RELATIONS)} relationships (idempotent)."
        )
    finally:
        driver.close()


def generate_pdfs() -> List[Path]:
    import fitz  # PyMuPDF — already a project dependency

    _DEMO_DIR.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for filename, title, paragraphs in _DOCS:
        doc = fitz.open()
        page = doc.new_page()
        y = 72
        page.insert_text((72, y), title, fontsize=16, fontname="helv")
        y += 36
        for para in paragraphs:
            # naive wrap at ~90 chars so long lines stay on the page
            for i in range(0, len(para), 90):
                page.insert_text(
                    (72, y), para[i : i + 90], fontsize=11, fontname="helv"
                )
                y += 18
            y += 10
        out = _DEMO_DIR / filename
        doc.save(str(out))
        doc.close()
        written.append(out)
    print(f"Generated {len(written)} demo PDFs in {_DEMO_DIR}")
    return written


def upload_pdfs(pdfs: List[Path]) -> None:
    import os

    import httpx

    base = os.environ.get("DEMO_API_BASE", "http://127.0.0.1:8000")
    user = os.environ.get("DEMO_USER")
    password = os.environ.get("DEMO_PASSWORD")
    if not user or not password:
        print("SKIP upload: set DEMO_USER and DEMO_PASSWORD env vars.")
        return
    with httpx.Client(base_url=base, timeout=60.0) as client:
        # OAuth2-style login endpoint takes FORM fields, not JSON.
        tok = client.post(
            "/api/v1/auth/login", data={"username": user, "password": password}
        )
        tok.raise_for_status()
        token = tok.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for pdf in pdfs:
            with pdf.open("rb") as fh:
                resp = client.post(
                    "/api/v1/documents/",
                    headers=headers,
                    files={"file": (pdf.name, fh, "application/pdf")},
                )
            print(f"  upload {pdf.name}: {resp.status_code}")
    print("Uploaded demo PDFs — indexing runs via the Celery pipeline.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load the industrial demo dataset.")
    parser.add_argument("--graph-only", action="store_true", help="seed KG only")
    parser.add_argument("--upload", action="store_true", help="upload PDFs to the API")
    args = parser.parse_args()

    # --graph-only seeds the KG and stops; otherwise seed the KG and also
    # generate (and optionally upload) the demo PDFs.
    seed_graph()
    if args.graph_only:
        return 0
    pdfs = generate_pdfs()
    if args.upload:
        upload_pdfs(pdfs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
