"""Risk scoring and routing to one of six outcomes."""
from __future__ import annotations

from enum import Enum

from .validation import Report


class Decision(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    AUTO_CORRECTED = "AUTO_CORRECTED"
    RETRY_WITH_SONNET = "RETRY_WITH_SONNET"
    PENDING_CONFIRM = "PENDING_CONFIRM"
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"


MAX_RETRIES = 2


def risk_score(report: Report) -> float:
    """0 = clean, 1 = unusable. Errors weigh more than warnings."""
    score = 0.30 * len(report.errors) + 0.05 * len(report.warnings)
    score += (1.0 - report.confidence_score) * 0.5
    return min(1.0, score)


def route(report: Report, retry_count: int = 0) -> Decision:
    risk = risk_score(report)
    conf = report.confidence_score

    if report.valid and risk < 0.3 and conf >= 0.9:
        return Decision.AUTO_APPROVED
    if report.valid and report.corrections and not report.errors:
        return Decision.AUTO_CORRECTED
    if report.errors and retry_count < MAX_RETRIES:
        return Decision.RETRY_WITH_SONNET
    if 0.75 <= conf < 0.90:
        return Decision.PENDING_CONFIRM
    if conf < 0.75 or retry_count >= MAX_RETRIES:
        return Decision.PENDING_REVIEW
    return Decision.BLOCKED
