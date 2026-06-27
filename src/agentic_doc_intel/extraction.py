"""VLM extraction: pdf pages -> images -> one Bedrock call with forced tool use.

No OCR, no regex. The model reads the page images directly and is forced to
return JSON matching the document schema.
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from typing import Any

import boto3
import fitz  # pymupdf

from .schemas import build_tool, system_prompt_for

DEFAULT_DPI = 150  # 300 costs ~4x the image tokens for no accuracy gain


@dataclass
class Extraction:
    data: dict[str, Any]
    confidences: dict[str, float] = field(default_factory=dict)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def pdf_to_pngs(pdf_path: str, dpi: int = DEFAULT_DPI) -> list[bytes]:
    """Render every page of a pdf to PNG bytes. A 3-page doc is ~3 images in <1s."""
    pages: list[bytes] = []
    with fitz.open(pdf_path) as doc:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            pages.append(pix.tobytes("png"))
    return pages


class VLMExtractor:
    """Wraps a single Bedrock `converse` call with a forced extraction tool."""

    def __init__(self, model: str, region: str = "us-east-1"):
        self.model = model
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def extract(self, pdf_path: str, doc_type: str, dpi: int = DEFAULT_DPI) -> Extraction:
        images = pdf_to_pngs(pdf_path, dpi=dpi)
        tool = build_tool(doc_type)

        content: list[dict[str, Any]] = [
            {"image": {"format": "png", "source": {"bytes": img}}} for img in images
        ]
        content.append({"text": "Extract the fields from these page images."})

        resp = self._client.converse(
            modelId=self.model,
            system=[{"text": system_prompt_for(doc_type)}],
            messages=[{"role": "user", "content": content}],
            toolConfig={
                "tools": [{"toolSpec": tool}],
                # force the model to call the tool, so output is always valid JSON
                "toolChoice": {"tool": {"name": tool["name"]}},
            },
            inferenceConfig={"temperature": 0.0, "maxTokens": 4096},
        )

        block = _first_tool_use(resp)
        if block is None:
            raise ExtractionError("model did not return a tool_use block")

        data = block["input"]
        usage = resp.get("usage", {})
        return Extraction(
            data=data,
            confidences=data.get("field_confidences", {}) or {},
            model=self.model,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )


def _first_tool_use(resp: dict[str, Any]) -> dict[str, Any] | None:
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]
    return None


class ExtractionError(RuntimeError):
    pass


def estimate_cost(ex: Extraction) -> float:
    """Haiku 4.5 on Bedrock: $0.80 / 1M input, $4.00 / 1M output."""
    return (ex.input_tokens / 1e6) * 0.80 + (ex.output_tokens / 1e6) * 4.00
