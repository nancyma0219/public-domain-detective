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

## Corrected local SQL diagnostics

### cohort_strict

`SELECT reg_year, COUNT(*) AS registration_rows, COUNT(DISTINCT regnum || '|' || COALESCE(regdate,'')) AS distinct_registration_keys, COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) AS matched_candidate_rows, ROUND(100.0 * COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) / NULLIF(COUNT(*),0), 2) AS candidate_link_rate_pct FROM reg_status WHERE regexp_matches(regnum, '^A[0-9]') AND reg_year BETWEEN 1931 AND 1963 GROUP BY reg_year ORDER BY reg_year`

```json
{
  "columns": [
    "reg_year",
    "registration_rows",
    "distinct_registration_keys",
    "matched_candidate_rows",
    "candidate_link_rate_pct"
  ],
  "rows": [
    [
      1931,
      9337,
      9304,
      2450,
      26.24
    ],
    [
      1932,
      8603,
      8568,
      2398,
      27.87
    ],
    [
      1933,
      7981,
      7954,
      2358,
      29.55
    ],
    [
      1934,
      8680,
      8645,
      2459,
      28.33
    ],
    [
      1935,
      8970,
      8940,
      2660,
      29.65
    ],
    [
      1936,
      9269,
      9225,
      2769,
      29.87
    ],
    [
      1937,
      9181,
      9160,
      2915,
      31.75
    ],
    [
      1938,
      9442,
      9441,
      3000,
      31.77
    ],
    [
      1939,
      9450,
      9449,
      3012,
      31.87
    ],
    [
      1940,
      10202,
      10200,
      3201,
      31.38
    ],
    [
      1941,
      9311,
      9308,
      3241,
      34.81
    ],
    [
      1942,
      8032,
      8027,
      3065,
      38.16
    ],
    [
      1943,
      6785,
      6779,
      2620,
      38.61
    ],
    [
      1944,
      6222,
      6213,
      2454,
      39.44
    ],
    [
      1945,
      6296,
      6291,
      2218,
      35.23
    ],
    [
      1946,
      8313,
      8293,
      2625,
      31.58
    ],
    [
      1947,
      8816,
      8794,
      3027,
      34.34
    ],
    [
      1948,
      9686,
      9659,
      3183,
      32.86
    ],
    [
      1949,
      10354,
      10332,
      3317,
      32.04
    ],
    [
      1950,
      11485,
      11457,
      4021,
      35.01
    ],
    [
      1951,
      11405,
      11393,
      3964,
      34.76
    ],
    [
      1952,
      12007,
      11994,
      3869,
      32.22
    ],
    [
      1953,
      27428,
      27416,
      4830,
      17.61
    ],
    [
      1954,
      38443,
      38410,
      5508,
      14.33
    ],
    [
      1955,
      40122,
      40087,
      5554,
      13.84
    ],
    [
      1956,
      38942,
      38919,
      5521,
      14.18
    ],
    [
      1957,
      41486,
      41463,
      6195,
      14.93
    ],
    [
      1958,
      42962,
      42930,
      6248,
      14.54
    ],
    [
      1959,
      46145,
      46119,
      6693,
      14.5
    ],
    [
      1960,
      47254,
      47233,
      6824,
      14.44
    ],
    [
      1961,
      51499,
      51489,
      6983,
      13.56
    ],
    [
      1962,
      54258,
      54205,
      7557,
      13.93
    ],
    [
      1963,
      53507,
      53457,
      8097,
      15.13
    ]
  ],
  "error": null
}
```

### year_diagnostics

`SELECT CASE WHEN reg_year IS NULL THEN 'null' WHEN reg_year BETWEEN 1923 AND 1977 THEN 'catalog_year_range_1923_1977' WHEN reg_year BETWEEN 1800 AND 2100 THEN 'plausible_year_outside_catalog_range' ELSE 'implausible_year' END AS year_category, COUNT(*) AS registration_rows, MIN(reg_year) AS min_year, MAX(reg_year) AS max_year FROM reg_status GROUP BY 1 ORDER BY 1`

```json
{
  "columns": [
    "year_category",
    "registration_rows",
    "min_year",
    "max_year"
  ],
  "rows": [
    [
      "catalog_year_range_1923_1977",
      2143050,
      1923,
      1977
    ],
    [
      "implausible_year",
      11,
      1,
      5764
    ],
    [
      "null",
      24915,
      null,
      null
    ],
    [
      "plausible_year_outside_catalog_range",
      1898,
      1837,
      1999
    ]
  ],
  "error": null
}
```

### duplicate_units

`SELECT COUNT(*) AS duplicated_regnum_groups, COALESCE(SUM(n),0) AS rows_in_duplicated_groups, COALESCE(SUM(n-1),0) AS excess_rows_over_one_per_regnum FROM (SELECT regnum, COUNT(*) AS n FROM reg_status WHERE regnum IS NOT NULL GROUP BY regnum HAVING COUNT(*)>1)`

```json
{
  "columns": [
    "duplicated_regnum_groups",
    "rows_in_duplicated_groups",
    "excess_rows_over_one_per_regnum"
  ],
  "rows": [
    [
      811084,
      1758932,
      947848
    ]
  ],
  "error": null
}
```

### cohort_breakdown

`SELECT CASE WHEN reg_year BETWEEN 1931 AND 1952 THEN '1931–1952' WHEN reg_year BETWEEN 1953 AND 1963 THEN '1953–1963' END AS period, COUNT(*) AS registration_rows, COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) AS linked_rows, ROUND(100.0*COUNT(*) FILTER (WHERE renewal_id IS NOT NULL)/NULLIF(COUNT(*),0),2) AS candidate_link_pct FROM reg_status WHERE regexp_matches(regnum,'^A[0-9]') AND reg_year BETWEEN 1931 AND 1963 GROUP BY 1 ORDER BY 1`

```json
{
  "columns": [
    "period",
    "registration_rows",
    "linked_rows",
    "candidate_link_pct"
  ],
  "rows": [
    [
      "1931–1952",
      199827,
      64826,
      32.44
    ],
    [
      "1953–1963",
      482046,
      70010,
      14.52
    ]
  ],
  "error": null
}
```
