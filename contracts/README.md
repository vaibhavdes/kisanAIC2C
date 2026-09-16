# Exchange contract v1.0.0 — draft

[practice-bundle.schema.json](practice-bundle.schema.json) defines the strict public shape. [The synthetic example](examples/synthetic-practice-bundle.json) is schema-valid but intentionally draft/unreviewed; it must not activate as advice.

This is an original application protocol for the demo, not an official AgriN or BRICS standard. Unknown properties are forbidden, including exact geometry and identity fields. This cannot detect personal information embedded in text: the application must add content inspection, an allowlist exporter and human review.

`c2c-demo-1` is a small local vocabulary, not an international crop taxonomy. Crop groups are cereals, pulses, oilseeds, vegetables and other; water contexts are rainfed, supplemental irrigation and irrigated. Map crop-specific local codes separately; no generic group is sufficient for agronomic eligibility. Season/climate text requires destination review, not fuzzy auto-approval.

Before activation require supported schema/vocabulary, permitted license, trusted upload/origin policy, origin review, local compatibility, local expert approval and non-synthetic status. Store destination review outside the source bundle. Synthetic bundles can demonstrate validation/rejection and sandbox review but cannot become live farmer advice.

Validate with JSON Schema Draft 2020-12 and a format checker. Check timestamps semantically (including no misleading future source review), URI safety, payload size and privacy separately. Source URLs are citations; do not automatically fetch arbitrary imported URLs. Digest/idempotency detection is receiver metadata and does not establish authenticity.

Future contract changes use versioning and explicit migration. Generate API OpenAPI/types during B01; do not use this exchange schema as the private farm-data model.
