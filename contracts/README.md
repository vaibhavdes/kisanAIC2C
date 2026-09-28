# Exchange contracts

JSON Schema (Draft 2020-12) documents that KISANAI nodes publish and import. They are an application protocol written for this project, not an official AgriN or BRICS standard.

| Schema | Content |
|---|---|
| [agronomy-pack.schema.json](agronomy-pack.schema.json) | A state's crop calendar: sowing windows per crop and season, irrigation needs, groundwater category, sowing regulations, priority practices, sources, licence and review status |
| [practice-bundle.schema.json](practice-bundle.schema.json) | One regenerative practice: steps, crops, seasons, water contexts, contraindications, sources and, when at least 5 outcomes exist, aggregated field evidence |

Conventions:
- Regions use ISO 3166-2 codes (`IN-MH`).
- Crops use catalog IDs plus scientific names.
- Practices use the practice codes in `data/practices/regenerative_practices.json`.
- Unknown properties are rejected, so bundles cannot carry farm geometry or identities.

Receiving node rules (implemented in `service.py`):
- import only from allowlisted peers or an expert's paste;
- validate against the schema;
- deduplicate by content digest;
- store the import as *pending*.

Nothing is used for farmer advice until a local expert approves it. An approved pack supersedes older versions for the same region.

Bump `schema_version` for any breaking change.
