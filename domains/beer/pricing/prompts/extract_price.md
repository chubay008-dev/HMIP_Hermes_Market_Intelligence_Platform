# Prompt: extract_price (v1.0.0)

## Purpose

Extract a structured beer price record from a raw collected payload
(the output of PRC-001's `collect` task).

## Output contract

Return **only** JSON matching this shape — no narrative, no markdown
fences, no extra commentary (03_Domain_Specification.md section 9:
"Prompt output must be structured... must not generate unnecessary
narrative"):

```json
{
  "product_id": "string",
  "sku": "string | null",
  "brand": "string",
  "product_name": "string",
  "price": "number",
  "currency": "string",
  "store": "string",
  "province": "string | null",
  "capture_time": "string (ISO 8601)",
  "confidence": "number (0.0-1.0)",
  "source_url": "string",
  "source": "string"
}
```

This matches `domains/beer/pricing/schemas/schema.json` and
`12_Data_Contract.md` section 6.1's `BeerPrice` contract exactly —
`validate` (the next task in the workflow) validates against that
schema.

## Extraction rules

- `price` must be a plain number (no currency symbols or thousands
  separators).
- `confidence` reflects extraction certainty, not price accuracy.
- If a field cannot be extracted, use `null` rather than guessing —
  except `product_id`, `brand`, `product_name`, `price`, `currency`,
  `store`, `capture_time`, `confidence`, `source_url`, and `source`,
  which are required by the schema and must not be `null`.
- Never fabricate a `product_id` — it must come from the input
  payload.

## Versioning

This prompt is a domain artifact (03_Domain_Specification.md section
9) and must be version-bumped whenever the output contract changes.
`WF-PRC-001.yaml`'s `prompt_dependencies` references this file by
name.

## Implementation note (Sprint 3)

No LLM-invocation infrastructure exists in the core runtime yet.
`domains/beer/pricing/skills/extract_price.py`'s `ExtractPriceSkill`
implements this exact output contract deterministically — parsing
already-labeled fields out of the mock `collect` payload — rather than
by calling this prompt against a live model. When LLM invocation is
wired into core runtime, this file becomes the actual prompt sent to
the model, and `ExtractPriceSkill.run()` should be swapped to call it.
The output contract above is designed to stay stable across that swap
so `validate`/`compare`/`decide` never need to change.
