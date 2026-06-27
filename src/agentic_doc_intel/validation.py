"""Deterministic validation. Runs after extraction, before anything downstream.

Pure python, no model calls, finishes in well under 10ms. The point is to catch
anything the VLM gets wrong (a bad total, an impossible date, a confused field)
before it reaches storage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

MONEY_TOL = 0.01   # qty * unit_price vs amount
TOTAL_TOL = 0.02   # sum(line items) vs total
DATE_MIN, DATE_MAX = date(2020, 1, 1), date(2030, 12, 31)

REQUIRED = {
    "acknowledgment": ["po_number", "vendor_name", "acknowledgment_number", "acknowledgment_date"],
    "purchase_order": ["po_number", "vendor_name", "po_date"],
}


@dataclass
class Report:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    confidence_score: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "correction_count": len(self.corrections),
            "confidence_score": round(self.confidence_score, 3),
        }


def validate(data: dict[str, Any], doc_type: str, confidences: dict[str, float] | None = None) -> Report:
    """Run all five rule groups. Mutates `data` in place for auto-corrections."""
    r = Report()
    _autocorrect(data, r)            # group 5 first, so later checks see clean values
    _financial(data, r)             # group 1
    _dates(data, r)                 # group 2
    _required(data, doc_type, r)    # group 3
    _cross_field(data, r)           # group 4

    r.valid = not r.errors
    r.confidence_score = _confidence(data, r, confidences or {})
    return r


# --- group 1: financial -----------------------------------------------------
def _financial(data: dict[str, Any], r: Report) -> None:
    items = data.get("line_items") or []
    running = 0.0
    for i, it in enumerate(items):
        qty, price, amount = it.get("quantity"), it.get("unit_price"), it.get("amount")
        if _is_num(qty) and _is_num(price) and _is_num(amount):
            if abs(qty * price - amount) > MONEY_TOL:
                r.errors.append(f"line {i}: qty*unit_price ({qty*price:.2f}) != amount ({amount:.2f})")
        if _is_num(amount):
            if amount < 0:
                r.errors.append(f"line {i}: negative amount {amount}")
            running += amount

    total = data.get("total_amount")
    if _is_num(total) and items:
        if abs(running - total) > TOTAL_TOL:
            r.errors.append(f"sum of line items ({running:.2f}) != total_amount ({total:.2f})")
    if _is_num(total) and total < 0:
        r.errors.append("negative total_amount")


# --- group 2: dates ---------------------------------------------------------
def _dates(data: dict[str, Any], r: Report) -> None:
    parsed: dict[str, date] = {}
    for key in ("order_date", "ship_date", "arrival_date", "po_date", "acknowledgment_date", "ack_date"):
        val = data.get(key)
        if not val:
            continue
        d = _parse_date(val)
        if d is None:
            r.errors.append(f"{key}: not a real date ({val!r})")
        elif not (DATE_MIN <= d <= DATE_MAX):
            r.errors.append(f"{key}: out of range ({val})")
        else:
            parsed[key] = d

    if "order_date" in parsed and "ship_date" in parsed and parsed["order_date"] > parsed["ship_date"]:
        r.errors.append("order_date is after ship_date")
    if "ship_date" in parsed and "arrival_date" in parsed and parsed["ship_date"] > parsed["arrival_date"]:
        r.errors.append("ship_date is after arrival_date")


# --- group 3: required fields ----------------------------------------------
def _required(data: dict[str, Any], doc_type: str, r: Report) -> None:
    for f in REQUIRED.get(doc_type, []):
        if data.get(f) in (None, ""):
            r.errors.append(f"missing required field: {f}")

    items = data.get("line_items") or []
    if not items:
        r.errors.append("document has no line items")
    for i, it in enumerate(items):
        for f in ("item_number", "quantity", "amount"):
            if it.get(f) in (None, ""):
                r.warnings.append(f"line {i}: missing {f}")


# --- group 4: cross-field ---------------------------------------------------
def _cross_field(data: dict[str, Any], r: Report) -> None:
    po, ack = data.get("po_number"), data.get("acknowledgment_number")
    if po and ack and po == ack:
        r.errors.append("po_number equals acknowledgment_number (likely confused)")

    vendor = (data.get("vendor_name") or "").strip().lower()
    for other in ("ship_to_name", "bill_to_name"):
        name = (data.get(other) or "").strip().lower()
        if vendor and name and vendor == name:
            r.errors.append(f"vendor_name equals {other} (vendor is not the customer)")


# --- group 5: auto-correction ----------------------------------------------
def _autocorrect(data: dict[str, Any], r: Report) -> None:
    NULLISH = {"n/a", "na", "-", "--", "none", ""}
    for key, val in list(data.items()):
        if isinstance(val, str):
            stripped = val.strip()
            if stripped != val:
                data[key] = stripped
                r.corrections.append(f"trimmed whitespace on {key}")
            if "date" in key:
                norm = _normalize_date(data[key])
                if norm and norm != data[key]:
                    data[key] = norm
                    r.corrections.append(f"normalized {key} to {norm}")

    for it in data.get("line_items") or []:
        for k in ("quantity", "unit_price", "amount"):
            if isinstance(it.get(k), str) and it[k].strip().lower() in NULLISH:
                it[k] = None
                r.corrections.append(f"line item {k}: '{it.get(k)}' -> null")
        # 1-cent rounding
        if _is_num(it.get("quantity")) and _is_num(it.get("unit_price")) and _is_num(it.get("amount")):
            expected = round(it["quantity"] * it["unit_price"], 2)
            if 0 < abs(expected - it["amount"]) <= MONEY_TOL:
                it["amount"] = expected
                r.corrections.append("fixed 1-cent rounding on a line item")


# --- helpers ----------------------------------------------------------------
def _confidence(data: dict[str, Any], r: Report, confidences: dict[str, float]) -> float:
    base = sum(confidences.values()) / len(confidences) if confidences else 0.9
    base -= 0.15 * len(r.errors)
    base -= 0.03 * len(r.warnings)
    return max(0.0, min(1.0, base))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%d %b %Y", "%Y/%m/%d")


def _parse_date(val: str) -> date | None:
    val = str(val).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_date(val: str) -> str | None:
    d = _parse_date(val)
    return d.isoformat() if d else None
