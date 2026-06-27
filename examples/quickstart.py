"""Minimal end-to-end example.

Requires AWS credentials with Bedrock access in your environment, and access to
the Haiku 4.5 / Sonnet 4 cross-region inference profiles.
"""
from agentic_doc_intel import DocumentIntelligence

engine = DocumentIntelligence()  # defaults to Haiku 4.5 extract, Sonnet 4 retry

result = engine.process("acknowledgment.pdf", doc_type="acknowledgment")

print("decision:  ", result.decision.value)
print("confidence:", result.confidence)
print("cost (usd):", result.cost_usd)
print("retries:   ", result.retries)
print("report:    ", result.report)

data = result.data
print("\nvendor:", data["vendor_name"])
print("po:    ", data["po_number"])
print("total: ", data["total_amount"])
print("items: ", len(data["line_items"]))

# route on the decision
if result.decision.value in ("AUTO_APPROVED", "AUTO_CORRECTED"):
    ...  # store straight through
else:
    ...  # send to the human review queue
