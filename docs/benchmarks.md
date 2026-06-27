# benchmarks

all figures are from the internal rebuild this library came out of, anonymized.
the labeled set is 15 documents (10 acknowledgments + 5 purchase orders, 127
header fields and 64 line items after a ground-truth audit). later rounds added
43 unseen documents and a 5-document live production run.

## approach comparison

| approach | docs processed | headers | line items | cost/doc | speed | failure rate |
|---|---|---|---|---|---|---|
| regex parser | 4 / 15 | 40% | 90%* | $0.03-0.05 | 52s+ | 73% |
| LLM mapper | 9 / 15 | 98% | 80% | $0.031-0.051 | 97s+ | 73%** |
| VLM direct | 15 / 15 | 90.6% | 73.6% | $0.007 | 8-12s | 0% |
| VLM + validation | 15 / 15 | 93.7% | 90.6% | $0.007 | 8-12s | 0% |

\* regex line items only measurable on the 4 docs that completed.
\*\* the LLM mapper still sits on top of the OCR step, which fails ~73% of the time on larger/scanned docs.

## compute footprint

| resource | regex | LLM mapper | VLM direct |
|---|---|---|---|
| OCR service | required | required | not needed |
| OCR sidecar/server | required | required | not needed |
| model calls | 0 | 1 | 1 |
| total services | 3 | 4 | 1 |

## ground-truth audit

reviewing all 15 pdfs by hand turned up two labeling errors that were unfairly
penalizing the model:

- one purchase order had 23 line items across 3 pages; the labels only had 12. the model had extracted all 23 correctly, so it was being scored 1/12 when it should have been ~23/23.
- one acknowledgment had a wrong item number in the labels; the unit price and amount matched what the model read, not the label.

after fixing the labels: headers 93.7% (119/127), line items 90.6% (58/64),
0 extraction failures.

## production run (live endpoint)

5 documents, 5 different vendors (anonymized), 41 line items total, every field
checked against the pdf by hand.

| metric | value |
|---|---|
| vendor accuracy | 5 / 5 |
| po number accuracy | 5 / 5 |
| total amount accuracy | 5 / 5 |
| line item recall | 41 / 41 |
| auto-approved | 5 / 5 |
| avg processing time | 16.3s |
| avg cost per doc | ~$0.01 |

## cost model

haiku 4.5 on bedrock: $0.80 / 1M input tokens, $4.00 / 1M output.
per document ~3k input (images + prompt) and ~1.5k output, so ~$0.008/doc.
sonnet retries add ~$0.02 each; at a 20% retry rate the blended cost is ~$0.012/doc.

## things worth knowing

- haiku 4.5 needs the cross-region inference profile id; the plain model id does not work on-demand.
- 150 dpi matches accuracy at 300 dpi for ~1/4 the image tokens.
- the 200k context takes 10+ page documents in one call, no splitting.
