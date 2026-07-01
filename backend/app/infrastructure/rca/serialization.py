"""Shared (de)serialization for RCASession — used by both the Postgres audit
repository and the Redis live-state store so the two never drift."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.domain.rca_brain.models import (
    RCAReport,
    RCASession,
    RCAStatus,
    WhyStep,
)


def session_to_dict(session: RCASession) -> Dict[str, Any]:
    return {
        "session_id": session.session_id,
        "asset_tag": session.asset_tag,
        "incident_description": session.incident_description,
        "status": session.status.value,
        "whys": [{"question": w.question, "answer": w.answer} for w in session.whys],
        "report": session.report.model_dump(mode="json") if session.report else None,
        "created_at": session.created_at.isoformat(),
    }


def session_from_dict(data: Dict[str, Any]) -> RCASession:
    report: Optional[RCAReport] = None
    if data.get("report"):
        report = RCAReport.model_validate(data["report"])
    return RCASession(
        session_id=data["session_id"],
        asset_tag=data["asset_tag"],
        incident_description=data["incident_description"],
        status=RCAStatus(data["status"]),
        whys=[
            WhyStep(question=w["question"], answer=w.get("answer"))
            for w in data.get("whys", [])
        ],
        report=report,
        created_at=datetime.fromisoformat(data["created_at"]),
    )
