# Arkive Design Patterns Worth Cribbing

*Research report, 2026-08-20. Source: read-only survey of `~/Documents/Git/arkive`
(migrations/001–007, src/db.js, src/authority.js, src/edtf.js, docs/HANDOFF.md).
Goal: crib patterns, NOT integrate — posa-wiki stays its own thing.*

## 1. Entity types and typed fields (EAV schema)

Two-table type system (`migrations/001_initial.sql`):

- `entity_types` (id, name, icon, color, `title_template`, sort_order, `deleted_at`) — user-definable types, not hardcoded classes.
- `field_definitions` (id, type_id FK, `name` display label, `key` — **frozen at creation**, `field_type` enum, `namespace`, required, sort_order, options JSON, deleted_at). Field types: `text, textarea, edtf, url, color, colors, tags, aliases, number, select, boolean, image_url`.
- `entities` (id, type_id, `title_cache` — derived title kept in sync on every write, hero_image, deleted_at).
- `entity_values` — EAV table, one row per `(entity_id, field_key)`, WITHOUT ROWID, PK `(entity_id, field_key)`; exactly one of `value_text / value_number / value_json / value_boolean` populated per field_type. EDTF dates store raw string + derived min/max ISO keys in value_json, mirroring `min` into value_text so ORDER BY/BETWEEN work at any precision.

**Namespace convention:** `field_definitions.namespace` is a free-text label like `dc:title`, `schema:sameAs`, `skos:altLabel`, `dbo:abstract`, `custom:foo` — documents the semantic mapping (Dublin Core / schema.org / SKOS) without an RDF store, AND serves as a behavioral hook: code finds "the field that means same-as" via `(namespace, field_type)` pairs (`matchingAuthorityFields(type, 'schema:sameAs', 'url')` in src/db.js) instead of hardcoding field keys.

**Schema-evolution invariant:** field keys are frozen forever; renaming only changes `name`. Removing a field soft-deletes the definition but **leaves entity_values rows in place** — orphaned values are a feature; re-adding the same key resurrects old data.

## 2. Controlled vocabulary / field-value reuse

No separate vocabulary table — vocabulary is *derived live from usage*:

- `GET /api/field-values?type_id=&field_key=` returns distinct values already used in that field of that type, **grouped case-insensitively** (`COLLATE NOCASE`), ordered by usage count, capped at 50. Scoping to (type, field) is required so vocabularies don't mix.
- Frontend discipline: `<datalist>` populated from field-values, with **case-snap on blur** — typing a near-match casing snaps to the existing value's casing *before save*. This is the real anti-duplicate mechanism.
- **Documented failure mode** (Arkive HANDOFF + adversarial review finding #6): case-insensitive grouping at *read* time is not enough — "Gothic" and "gothic" still accumulate as distinct rows that only look merged in aggregate views. Lesson: **snap to canonical casing at write time** (look up existing casing before insert and reuse it).
- Field-role discipline enforced by policy, not schema: genre-like field (`dc:type`) vs carrier field (`dc:format`) must never receive the same word — analogous to posa-wiki's validated/unvalidated split, enforced via suggestion UI/agent instructions rather than DB constraints.

## 3. Typed bidirectional links

- `relation_types` table: `name` (PK), `inverse_name`, `namespace`, `inverse_namespace`, `color`. Seeded pairs: `related/related`, `references/referenced_by`, `part_of/has_part`, `created_by/created`, `depicts/depicted_in`, `documents/documented_by`. Namespaces map to dcterms/foaf where a good match exists, NULL otherwise. Relation vocabulary is runtime-extensible.
- `links` table: `id, source_id, target_id (nullable), target_uri (nullable), target_label, relation_type FK, note` with a CHECK that exactly one of target_id/target_uri is set — **one table unifies internal entity links and external URI references**.
- Anti-dupe: partial unique indexes on `(source_id, target_id, relation_type)` and `(source_id, target_uri, relation_type)`; data layer also rejects the mirror duplicate for self-inverse relations (A→B `related` blocks B→A `related`).
- **Links stored once, directionally** — the inverse view is synthesized at read time by swapping in inverse_name. Bidirectionality is a read-time projection, not two mirrored rows.

Minimal recipe for posa-wiki relationships: one relation_types lookup with forward+inverse label pairs, one links table with entity-vs-external discriminator, partial unique indexes, inverse synthesized at query time.

## 4. Authority control (schema:sameAs)

No local authority/crosswalk table — field-driven plus a stateless resolver:

- Any `url` field with namespace `schema:sameAs` is "the" authority field for its type; any type opts into authority linking just by adding such a field.
- `src/authority.js parseAuthorityUrl`: validates http/https, no credentials/odd ports, must match a known authority URL shape. Wikidata supported; VIAF and LoC **recognized-but-unsupported** (clear "not implemented" message vs. generic parse failure) — recognize-and-explain is a good pattern.
- Lookups are live upstream fetches (Wikidata wbgetentities, optional Wikipedia/Commons rungs) with a 24h in-memory TTL cache, returning a **proposal** (add/conflict rows per field) that the caller applies explicitly — never silently overwriting curated data. Conflict rows on curated records default to *unchecked* ("the display name is chosen, not derived").
- For posa-wiki: (a) mark canonical-term fields by namespace/role, not a special table; (b) store the canonical identifier as a plain field value; (c) external enrichment (Wikidata for locations etc.) = on-demand fetch-and-propose, never direct write.

## 5. Other reusable patterns

- **Soft-delete + purge:** `deleted_at TEXT` (NULL = live) doubles as the retention timestamp; `purgeDeleted(days=30)` hard-deletes past the cutoff in one transaction, removing FTS rows first (FTS5 has no FK cascade). Posa-wiki already has deleted_at columns (migration 005) — the purge job pattern is the missing half.
- **Tags as JSON + normalized projection:** tags stored as JSON array on the row, PLUS a synced `entity_tags(entity_id, tag COLLATE NOCASE)` projection table purely for fast filtering/counting without json_each scans. Directly applicable to videos.validated_tags/unvalidated_tags.
- **EDTF dates** (`src/edtf.js`, zero-dep pure functions): year/month/day/decade/century/season/intervals + `~ ? %` qualifiers → `{edtf, min, max, display}`. Ready spec to port to Python if fuzzy dates ever needed.
- **Vocabulary-table migration cautionary tale** (migrations/007 comment): adding a real FK via create-copy-drop-rename silently fired ON DELETE CASCADE on an unrelated child table because `PRAGMA foreign_keys` is a no-op mid-transaction — validate vocabulary membership at the app layer instead, cascade renames explicitly in one transaction.
- **FTS5 field weighting:** separate `title`/`body`/`tags` FTS columns (enables BM25 per-field weighting), IDs kept UNINDEXED, tag arrays rendered into the tags column — tag search rides full-text without a join. Synced in-transaction on every write, never lazily.
- **Suggest-relation fields:** a field's `options.suggest = {type_id, relation}` makes one picker both fill the field and create the typed link — nice UX for "people/dogs in this video" edit forms.
