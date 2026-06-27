"""Per-document-type schemas, tool builders, and system prompts.

Adding a document type is three things: a schema, a system prompt, and the
validation rules (those live in validation.py). No framework changes.
"""
from __future__ import annotations

from typing import Any

_LINE_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["item_number", "quantity", "unit_price", "amount"],
    "properties": {
        "item_number": {"type": ["string", "null"]},
        "quantity": {"type": ["number", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "amount": {"type": ["number", "null"]},
    },
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "acknowledgment": {
        "type": "object",
        "additionalProperties": False,
        "required": ["po_number", "vendor_name", "total_amount", "line_items", "field_confidences"],
        "properties": {
            "po_number": {"type": ["string", "null"]},
            "vendor_name": {"type": ["string", "null"]},
            "acknowledgment_number": {"type": ["string", "null"]},
            "acknowledgment_date": {"type": ["string", "null"]},
            "customer_number": {"type": ["string", "null"]},
            "terms": {"type": ["string", "null"]},
            "ship_to_name": {"type": ["string", "null"]},
            "total_amount": {"type": ["number", "null"]},
            "line_items": {"type": "array", "items": _LINE_ITEM},
            "field_confidences": {"type": "object"},
        },
    },
    "purchase_order": {
        "type": "object",
        "additionalProperties": False,
        "required": ["po_number", "vendor_name", "total_amount", "line_items", "field_confidences"],
        "properties": {
            "po_number": {"type": ["string", "null"]},
            "vendor_name": {"type": ["string", "null"]},
            "po_date": {"type": ["string", "null"]},
            "ship_to_name": {"type": ["string", "null"]},
            "bill_to_name": {"type": ["string", "null"]},
            "terms": {"type": ["string", "null"]},
            "total_amount": {"type": ["number", "null"]},
            "line_items": {"type": "array", "items": _LINE_ITEM},
            "field_confidences": {"type": "object"},
        },
    },
}

_PROMPTS = {
    "acknowledgment": (
        "You read order acknowledgment documents. Extract exactly the fields in the tool schema. "
        "The vendor is the company that issued the acknowledgment (usually on the letterhead), not "
        "the customer it is sent to. Read values from the page images directly. If a field is not "
        "present, return null. For field_confidences, give a 0-1 score per top-level field."
    ),
    "purchase_order": (
        "You read purchase order documents. Extract exactly the fields in the tool schema. On a PO "
        "the vendor is the recipient (the supplier being ordered from), not the buyer. Capture every "
        "line item, one row per item. If a field is not present, return null. For field_confidences, "
        "give a 0-1 score per top-level field."
    ),
}


def build_tool(doc_type: str) -> dict[str, Any]:
    if doc_type not in SCHEMAS:
        raise KeyError(f"unknown doc_type {doc_type!r}; have {list(SCHEMAS)}")
    return {
        "name": "extract_document",
        "description": "Extract the structured fields from the document page images.",
        "inputSchema": {"json": SCHEMAS[doc_type]},
    }


def system_prompt_for(doc_type: str) -> str:
    return _PROMPTS.get(doc_type, _PROMPTS["acknowledgment"])
