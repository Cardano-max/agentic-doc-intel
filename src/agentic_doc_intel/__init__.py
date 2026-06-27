"""agentic-doc-intel: VLM document extraction with deterministic validation.

    from agentic_doc_intel import DocumentIntelligence

    engine = DocumentIntelligence()
    result = engine.process("doc.pdf", doc_type="acknowledgment")
    print(result.decision, result.confidence)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decision import Decision, route
from .extraction import Extraction, VLMExtractor, estimate_cost
from .validation import Report, validate

__version__ = "0.1.0"
__all__ = ["DocumentIntelligence", "Result", "Decision"]

HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET = "us.anthropic.claude-sonnet-4-20250514-v1:0"


@dataclass
class Result:
    data: dict[str, Any]
    decision: Decision
    confidence: float
    report: dict[str, Any]
    cost_usd: float
    retries: int


class DocumentIntelligence:
    """Render -> extract -> validate -> route, with a Sonnet retry on failure."""

    def __init__(self, model: str = HAIKU, retry_model: str = SONNET, region: str = "us-east-1"):
        self._haiku = VLMExtractor(model, region=region)
        self._sonnet = VLMExtractor(retry_model, region=region)

    def process(self, pdf_path: str, doc_type: str) -> Result:
        ex = self._haiku.extract(pdf_path, doc_type)
        report = validate(ex.data, doc_type, ex.confidences)
        decision = route(report, retry_count=0)
        cost = estimate_cost(ex)
        retries = 0

        while decision == Decision.RETRY_WITH_SONNET and retries < 2:
            retries += 1
            ex = self._sonnet.extract(pdf_path, doc_type)  # same images, stronger model
            report = validate(ex.data, doc_type, ex.confidences)
            decision = route(report, retry_count=retries)
            cost += estimate_cost(ex)

        return Result(
            data=ex.data,
            decision=decision,
            confidence=report.confidence_score,
            report=report.as_dict(),
            cost_usd=round(cost, 4),
            retries=retries,
        )
