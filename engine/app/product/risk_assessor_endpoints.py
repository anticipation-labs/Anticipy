"""HTTP surface for the V7 risk assessor.

Single endpoint:

  POST /api/risk/assess
    body: {"intent": <str|dict>, "binding": {...}, "memory_context": {...}}
    returns: RiskAssessment as JSON (see `risk_assessor.RiskAssessment`).

The handler never returns `decline`. Bad input falls back to a
`silent` low-risk default rather than 5xx so callers can keep moving
forward under the never-decline directive.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.product.risk_assessor import RiskAssessment, assess, explain


router = APIRouter()


class AssessBody(BaseModel):
    intent: Any = Field(default="", description="Free-form intent or dict")
    binding: Optional[dict[str, Any]] = Field(
        default=None,
        description="ActionBinder output (surface_target, "
                    "do_not_touch_warnings, missing_slots, recipients)",
    )
    memory_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Scoped memory snapshot (relationship_sensitive, etc.)",
    )


def _safe_assess(body: AssessBody) -> RiskAssessment:
    try:
        return assess(body.intent, body.binding, body.memory_context)
    except Exception as exc:  # pragma: no cover - defensive
        return RiskAssessment(
            level="low",
            proceed_mode="silent",
            confirm_card_required=False,
            reasons=[f"assessor_error_fell_back: {type(exc).__name__}"],
        )


@router.post("/api/risk/assess")
def assess_endpoint(body: AssessBody) -> JSONResponse:
    assessment = _safe_assess(body)
    out = assessment.to_dict()
    out["explanation"] = explain(assessment)
    if out.get("proceed_mode") == "decline":
        out["proceed_mode"] = "ask"
        out.setdefault("reasons", []).append(
            "normalized: never-decline contract"
        )
    return JSONResponse(out)


__all__ = ["router"]
