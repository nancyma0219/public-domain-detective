# Research quality audit

Heuristic quality flags from saved live traces; **not** independent legal fact verification.

## clarification

- No known heuristic flags. Manual review still required.

## patterns

- **error — unqueried_source**: Report says a HathiTrust search had no match, but hathitrust_lookup was never called.
- **error — unqueried_source**: Report says a Project Gutenberg search had no match, but gutenberg_search was never called.
- **error — unqueried_source**: Report says a Open Library search had no match, but openlibrary_search was never called.
- **warning — wrong_report_template**: Aggregate question should present research findings, not a book-specific copyright verdict.
- **error — rate_label**: Matched-link rate in transcriptions is not an observed legal renewal rate; name cohort and numerator.
- **error — duplicate_units**: SQL counts 811,084 regnum GROUPS with COUNT(*)>1, not 811,084 registration ROWS.
- **error — year_scope**: Filter <1923 OR >1969 includes legitimate 1970–1977 volumes in deployment. Must separate valid out-of-scope from invalid parsed years.
- **error — class_prefix_scope**: SQL regnum LIKE 'A%' also includes AF, AFO, AI and other A* prefixes; use regexp ^A[0-9].
- **warning — irrelevant_access_section**: Aggregate yearly research question does not ask for digitized copies; omit access section.
- **warning — false_gap**: SQL aggregate case was flagged as needing individual registration lookup; Gap Review is not query-type aware.

## renewed

- **error — unqueried_source**: Report says a HathiTrust search had no match, but hathitrust_lookup was never called.

## unresolved

- **error — rule_cited_for_search**: Legal-rule citation alone does not support a negative renewal-database search.

## variants

- **error — overclaimed_conflict_resolution**: Variants reported as fully reconciled or OCR error without authoritative confirmation of AI5926 discrepancy.
