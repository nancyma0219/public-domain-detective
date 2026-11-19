# Public Domain Detective

**A historical copyright record can decide whether a forgotten book may be translated, reprinted, narrated, or made accessible—but finding that record is rarely a simple search.**

For U.S. books published before 1964, copyright status can turn on a timely renewal, the identity of the *particular edition*, and whether the work qualifies for an exception such as restored protection for certain foreign works. Evidence is scattered across decades of **Catalog of Copyright Entries (CCE)** volumes, renewal indexes, and modern bibliographic catalogs. A failed title search is **not** proof that a work was never renewed. Conversely, finding a renewal for a similar title is not proof that it belongs to the edition in question.

This is consequential for **independent publishers, translators, audiobook producers, librarians, educators, digitization projects, and readers**: uncertainty can keep culturally valuable books out of circulation, while an unsupported “public domain” claim can expose reusers to legal risk. It is also an unusually good test of data-driven AI: the answer often lives in a specific historical row that a language model cannot reliably recall, and conflicting records must be *investigated*, not just summarized.

**Public Domain Detective** is a Deep Research agent that investigates those records, explains what the evidence establishes, and visibly distinguishes a supported conclusion from an unresolved gap. It also explores **historical patterns in registration-to-renewal linkages**, while carefully separating database match rates from legal renewal rates. **It provides research leads, not legal clearance or legal advice.**

## Who can use it, and what can they ask?

The web interface offers three research starting points, plus a free-text question box:

| Mode | Example of a useful question | What the user receives |
|---|---|---|
| **Investigate a book** | Is *Strangers on a Train* (1950) in the U.S. public domain? | Copyright assessment, registration and renewal evidence, term calculation, access information, limitations. |
| **Compare records** | Why does *The World of Carbon* have different original-registration references under renewal `RE277631`? | Confirmed associations, conflicting fields, unresolved discrepancies, and a **separate** copyright-status finding. |
| **Explore trends** | How did Class A registration-to-renewal linkage change from 1931 to 1963? | Reproducible SQL evidence, cohort definitions, a chart, annual data, period comparison, and competing explanations for anomalies. |

Underspecified questions (e.g., “Is my grandmother's old novel free to use?”) are answered with a **clarifying question before research starts**.

## Why use an agent instead of just asking an LLM?

The core challenge is **source-specific evidence**: registration numbers, renewal numbers, dates, pseudonyms, and edition relationships cannot be safely guessed from general knowledge. The agent can search an indexed historical corpus, inspect candidate links, consult book metadata, and perform follow-up research when records disagree. In the Asimov example, the important finding is not simply a copyright verdict: it is that **one renewal identifier is associated with differing original-registration references and dates**. That discrepancy survives into the final report instead of being silently resolved.

The same principle applies to aggregate questions. A naive query may accidentally include foreign/ad interim registration classes, count duplicate keys as books, or call a transcription-based candidate match a legal “renewal rate.” The agent uses a separately validated cohort computation for the supported annual Class A investigation and reports its numerator, denominator, provenance, and limitations.

## Data: origins, processing, and provenance

| Data source | What we use | How it is accessed / reproduced |
|---|---|---|
| [NYPL Catalog of Copyright Entries project](https://github.com/NYPL/catalog_of_copyright_entries_project) | Transcribed historical registration entries (title, author, registration number/date, publisher, source XML). | Download/clone the NYPL XML volumes and run the offline data preparation step. The application reads prepared `data/reg_status_*.parquet` with DuckDB. |
| [NYPL CCE renewals](https://github.com/NYPL/cce-renewals) | Renewal identifiers, dates, cited original registration numbers/dates, claimants, and source TSV. | Download/clone the renewal TSV files and prepare `data/renewals.parquet`. The code supports exact-key and candidate-level evidence checks. |
| [Open Library Search API](https://openlibrary.org/dev/docs/api/search) and [Authors API](https://openlibrary.org/developers/api) | Work/edition metadata, first-publication year, OCLC/LCCN identifiers, pseudonyms, author dates. | Live requests via `openlibrary_search` and `openlibrary_author`; author authority records are not automatically merged merely because names match. |
| [HathiTrust Bibliographic API](https://www.hathitrust.org/bib_api) | Bibliographic matches, item-level rights/access codes. | Live `hathitrust_lookup` when a usable identifier is available. **Digital access is not the same as copyright status.** |
| [Project Gutenberg catalog](https://www.gutenberg.org/ebooks/offline_catalogs.html) | Potential freely accessible digitized editions. | Optional catalog-based `gutenberg_search`, subject to local catalog availability and coverage. A non-match is source-scoped only. |
| [U.S. Copyright Office Circular 22](https://www.copyright.gov/circs/circ22.pdf) and [Circular 15A](https://www.copyright.gov/circs/circ15a.pdf) | Copyright investigation guidance and duration rules. | Deterministic `check_us_status` logic and `RULE:` citations; exceptions still require additional evidence. |

The project uses **DuckDB** to query registration and renewal Parquet files. Core logical tables/views include `reg_status` (one or more registration rows with candidate renewal fields) and `renewals` (renewal transcriptions). Research outputs use source IDs such as `REG:`, `REN:`, `SQL:`, `OL:`, `HT:`, and `RULE:`. They identify the *type and origin* of the evidence, not a legal certification.

### Loading the historical corpus

From the repository root, acquire the raw files:

```bash
git clone --depth 1 https://github.com/NYPL/catalog_of_copyright_entries_project data/nypl_registrations
git clone --depth 1 https://github.com/NYPL/cce-renewals data/nypl_renewals
```

The repository's offline preparation workflow parses the registrations' XML and the renewal TSVs, normalizes lookup fields, and writes Parquet files read by `records.py`. **The exact build command depends on the preparation script included in the submitted repository:** see `scripts/build_data.py` if present, or the repository's `prepare_agent_data.py`/`load_nypl.py` workflow. The deployed app needs these **prepared Parquet data files** (either shipped with the image or fetched from managed storage); raw XML/TSV downloads are not required for every request.

> **Data boundaries.** CCE transcriptions can have missing records, OCR errors, duplicate registration numbers, unexpected catalog-year assignments, and non-one-to-one relationships between registrations and renewals. Missing links cannot establish that a work is public domain. Foreign works, later editions, translations, images, and new material require separate consideration.

## Data Preparation and Reproducibility

The historical corpus is an **assembled research dataset, not a live copyright-office database**. The project combines previously collected historical CCE material with NYPL's published registration and renewal transcriptions, then prepares a local, queryable representation for evidence retrieval. The work involved identifying relevant source volumes/files, parsing heterogeneous XML and TSV entries, retaining source references, and constructing candidate links between original registrations and renewals. The resulting dataset supports both single-work investigations and cohort-level SQL research.

### From source files to the research tables

| Stage | Input | Processing / output | Why it matters |
|---|---|---|---|
| **Acquire** | Historical CCE registration XML and renewal TSV files, from the NYPL repositories linked above; previously collected material where applicable | Keep the original files and their source-volume/file identifiers | Researchers can trace an extracted entry back to its transcription source. |
| **Parse and standardize** | Heterogeneous historical records | Extract registration and renewal identifiers, dates, titles, claimants, and source metadata into the prepared Parquet dataset | Enables consistent searches across decades and formats without treating every record as error-free. |
| **Link candidates** | Original-registration references in renewal entries and the registration corpus | Build lookup fields and **candidate** associations; preserve multiple references and contradictory values rather than forcing a one-to-one match | A shared or missing key is not, by itself, proof of legal status. |
| **Query and audit** | `data/reg_status_*.parquet` and `data/renewals.parquet` | DuckDB-backed `reg_status` / `renewals` views, source-tagged evidence, and the validated Class A annual-cohort analysis | Makes the three sample queries reproducible against the same local corpus. |

**Data inventory.** The prepared research snapshot used during development contained approximately **2.17 million registration rows** and **445,000 renewal rows**. These figures describe rows in the loaded transcriptions, **not distinct copyrighted books** or verified legal renewals. Duplicate identifiers, missing or conflicting dates, and mismatched registration classes make that distinction important.

### Reproducing the data-dependent results

1. Obtain the public source datasets from the links in **Data: origins, processing, and provenance**. If using an independently collected historical snapshot, document its source and acquisition date separately; independently scraped files are **not assumed to be covered by NYPL's redistribution terms**.
2. Run the project's actual ingestion/preparation workflow to produce the Parquet files expected by `records.py`. The **exact command and input paths must be verified against the submitted scripts**; do not assume a script name that is not in the repository. A data package can instead supply the prepared Parquet files directly if raw-source ingestion is impractical for grading.
3. Verify that `data/reg_status_*.parquet` and `data/renewals.parquet` are present before starting `uv run app.py`. Record file sizes, row counts, and the data snapshot/version in the submission or a data manifest, so a grader knows which corpus was queried.
4. Re-run the three sample questions above. For the trends example, use the exact `cohort_research.py` definition: `reg_year` between 1931 and 1963, with `regexp_matches(regnum, '^A[0-9]+$')`; count **registration rows** and rows with a non-null candidate `renewal_id`. Different filters or dataset versions can change the percentages.
5. Preserve the `REG:`, `REN:`, and `SQL:` evidence identifiers in the results. Reproduction means checking the **underlying rows and method**, not merely seeing the same sentence in the final report.

**What should be shared.** The GitHub repository should include the ingestion/normalization code, schema or data dictionary, source links, an example or manifest of the prepared files, and the saved baseline evaluation. If the full corpus exceeds practical GitHub limits, the large raw files and/or Parquet snapshot may be provided as a separately downloadable archive or cloud-hosted dataset; the README should then state its **actual location, access steps, and version/checksum**. Cloud Run must have access to the prepared files at runtime, whether bundled in the container or retrieved from storage.

**Reuse and limitations.** Before publicly redistributing previously scraped source files, check each original source's terms and licensing, and do not include credentials or restricted material. The NYPL transcriptions are historical research evidence, not authoritative determinations of copyright status. A missing candidate renewal link is **not** a public-domain finding; similarly, an observed change in candidate linkage is **not** proof of a change in authors' renewal behavior.

## Research architecture

```text
User question
  │
  ▼
Lead ── vague? ──► Clarifying question (no researchers or database search)
  │
  ├── One parallel dispatch to fresh-context Researchers
  │     ├── Historical CCE registrations / renewals
  │     ├── Edition, bibliographic, and author evidence
  │     └── Access, rights codes, or SQL analysis as relevant
  │
  ├── Evidence-gap review ── material gaps? ──► second bounded research round
  │
  ▼
Writer (question-aware report)
  │
  ├── Citation / evidence-to-claim checks
  ├── Record-link and unsupported-claim safeguards
  └── For annual Class A analysis: deterministic CohortAudit SQL + validation
  ▼
Answer-first UI + cited records + optional research trace
```

`research.py` implements the **Lead, Researcher, and Writer** with distinct tasks. Researchers run in parallel and receive fresh contexts. The Lead can authorize another round when findings leave material gaps; the code caps the number of rounds (`MAX_ROUNDS = 2`) and researchers per round (`MAX_PER_ROUND = 4`). Evidence tools are implemented through `records.py` and `evidence_verification.py`; `gap_review.py`, `citation_guard.py`, `report_guard.py`, and `quality_guard.py` help detect missing sources, unsupported conclusions, and invalid cohort claims. `cohort_research.py` separately computes the supported annual SQL cohort from actual database results.

The `/chat` response preserves the assignment's required work trace: `tool_calls` contains **each agent's name**, tool name, arguments, and output. The interface makes this trace optional for readers while keeping it accessible to graders.

## Three sample queries for the grader

All three questions have been **run against the live local agent**. The answers below summarize the observed results, not hypothetical outcomes. Each is intentionally different: an established link, a conflicting-record investigation, and a full-dataset statistical inquiry.

### 1. Book status: an identified renewal

**Paste this query:**

> Is *Strangers on a Train* by Patricia Highsmith (1950) in the public domain in the United States?

**Expected / observed agent answer:** **No. In copyright in the U.S. through December 31, 2045**, with expected public-domain entry on January 1, 2046, assuming the stated conditions. The original Harper registration is `A41904`, dated **March 15, 1950**; renewal `R663598`, dated **June 6, 1977**, corresponds to that original work. A later French translation carries separate registration/renewal evidence and should not be confused with the U.S. original.

**Evidence to check:** `reg_status.regnum = 'A41904'` (`REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD`); `renewals.id = 'R663598'` and `renewals.oreg = 'A41904'` (`REN:R663598`, source renewal file `1977-1.tsv`); Circular 15A / 22; optional [Open Library work `OL59482W`](https://openlibrary.org/works/OL59482W).

### 2. Compare records: a real discrepancy that is not fully resolved

**Paste this query:**

> Why does Isaac Asimov's *The World of Carbon* have different original registration numbers associated with renewal `RE277631`? What is verified and unresolved?

**Expected / observed agent answer:** **Record discrepancy remains open**, even though the 1958 domestic registration `A352575` (August 22, 1958) has a strongly supported renewal link to `RE277631` (January 6, 1986), consistent with U.S. protection **through 2053**. The same renewal identifier is also associated in the transcribed records with an ad interim reference `AI5926`. The standalone registration transcription gives **April 1, 1953**, while renewal-side evidence gives **April 1, 1958**. Both dates must be reported; **the cause of the discrepancy has not been independently confirmed**. A 1962 revised-edition registration `A557886` and renewal `RE476868` should be treated separately.

**Evidence to check:** `reg_status` registration rows `A352575` (`REG:14A88E33-72C4-1014-84F6-87703AD4166D`) and `AI5926` (`REG:44CCD50E-7240-1014-AB88-AD98078397AF`); `renewals.id = 'RE277631'`, comparing each `oreg` and `odat` row/variant; 1962 `A557886` and `RE476868`; optional [Open Library work `OL46380W`](https://openlibrary.org/works/OL46380W).

### 3. Explore trends: the discontinuity around 1953

**Paste this query:**

> For U.S. Class A books registered from 1931 to 1963, how did the candidate renewal-linkage share change by year? Investigate the break near 1953.

**Expected / observed agent answer:** The **transcription-based candidate linkage share** differs sharply between periods: **32.74%** for 1931–1952 (**64,826 / 197,987 registration rows**) versus **14.62%** for 1953–1963 (**70,010 / 478,760 rows**). From 1952 to 1953, the denominator rises from **11,951** to **27,180** registration rows while linkage drops from **32.37%** to **17.77%**. This is **not a measured legal renewal rate**, and the database queries do **not** establish what caused the break. Plausible questions for further investigation include source coverage, record-type composition, year assignment, and exact-key matching quality.

**Evidence to check:** `reg_status` in DuckDB; annual and period queries defined in `cohort_research.py` and exposed as `SQL:` evidence. **Cohort:** `reg_year BETWEEN 1931 AND 1963` and `regexp_matches(regnum, '^A[0-9]+$')`. **Denominator:** qualifying registration *rows*, not unique books. **Numerator:** rows with a non-null candidate `renewal_id`. Source-file coverage diagnostics cover 1951–1954. The UI plots the verified annual SQL rows and allows the full 33-year table to be expanded.

### Same-model no-tool baseline: actual observed comparison

For the **exact same three sample questions** above, we also queried `vertex_ai/gemini-3.5-flash` using a **single user message with no system prompt, no tools, and no project data**. The table compares the observed outputs; the complete, unedited baseline responses are included immediately below and saved as [`evaluation/baseline/no_tool_answers.json`](evaluation/baseline/no_tool_answers.json) and [`evaluation/baseline/comparison.md`](evaluation/baseline/comparison.md). The baseline was actually run, not simulated.

| Sample query | Public Domain Detective — observed answer with tools | Same Gemini model — observed no-tool answer | What the comparison shows |
|---|---|---|---|
| **1. Strangers on a Train** | **In copyright through 2045**; original `A41904` and matching renewal `R663598` with dates and source provenance. | **Also answered in copyright until 2045**, and correctly gave public-domain entry in 2046; did **not** supply the original or renewal record numbers or source rows. | The value added here is **auditable original-record evidence**, not a change to the high-level conclusion. |
| **2. The World of Carbon** | Found original `A352575`, ad interim `AI5926`, and renewal `RE277631`; kept the **1953 vs. 1958** transcription disagreement unresolved. | Asserted original `A339834`, linked `A364874` from *The World of Nitrogen*, and claimed a **January 16, 1986** renewal, without tools or supporting records. | These specific claims **conflict with the project's retrieved NYPL rows** (`A352575`, `AI5926`, renewal **January 6, 1986**). The agent supports its assertions and leaves the date discrepancy open. |
| **3. 1931–1963 trends** | Computed strict-Class-A row-level candidate linkage: **32.74%** (1931–1952) versus **14.62%** (1953–1963), with a **downward** break near 1953 and unresolved causes. | Claimed rates rose from **7–10%** in earlier decades to **over 20%** by 1960–1963, describing an **upward** 1953 break and confidently attributing it to law and digitization changes. | Baseline trend and causal assertions **are not supported by, and contradict, the observed project cohort results**. The agent derives numbers from SQL and does not infer an unverified cause. |

**Interpretation.** A no-tool model can know the general doctrine and can even get a familiar title's final answer right. The difference is whether the answer is **reproducible from specific records**, separates title/edition variants, and distinguishes a measured linkage statistic from a causal historical explanation. These are three illustrative case studies, **not** an estimated overall model accuracy or controlled benchmark. The no-tool output is reproduced verbatim below, including statements not verified by the project; those statements are **model outputs, not endorsed historical facts**.

<details>
<summary><strong>Unedited no-tool baseline 1: Strangers on a Train</strong></summary>

**No**, *Strangers on a Train* by Patricia Highsmith (published in 1950) is **not** in the public domain in the United States.

Under U.S. copyright law, works published between 1928 and 1977 are protected for **95 years** from their date of publication, provided that their copyright was properly registered and renewed in its 28th year.

Because the copyright for *Strangers on a Train* was successfully renewed, it remains protected. It is currently scheduled to enter the public domain in the United States on **January 1, 2046**.

Currently, the rights to Patricia Highsmith's works are actively managed and protected by her estate (represented by the Swiss publisher Diogenes Verlag).

</details>

<details>
<summary><strong>Unedited no-tool baseline 2: The World of Carbon</strong></summary>

The discrepancy surrounding the copyright renewal **RE277631** for Isaac Asimov’s ***The World of Carbon*** (originally published in 1958) is a classic issue encountered in copyright clearance databases (such as the Stanford Copyright Renewal Database or Project Gutenberg's verification logs).

Here is a breakdown of why different original registration numbers are associated with this renewal, what has been verified, and what remains unresolved.

---

### Why Are There Different Original Registration Numbers?

The confusion of multiple original registration numbers associated with renewal **RE277631** stems from three main factors:

1. **The Companion Book (*The World of Nitrogen*):**
   In 1958, Asimov published two closely related companion chemistry books with the publisher Abelard-Schuman: *The World of Carbon* and *The World of Nitrogen*.
   * **The World of Carbon** was registered as **A339834** (published May 9, 1958).
   * **The World of Nitrogen** was registered as **A364874** (published November 7, 1958).

   Decades later, on **January 16, 1986**, Asimov renewed the copyrights for both books simultaneously. The Library of Congress processed them back-to-back:
   * *The World of Carbon* was renewed under **RE277631**.
   * *The World of Nitrogen* was renewed under **RE277632**.

   Because these books are thematic sequels, were published in the same year, and were renewed on the exact same day, automated database scrapers and manual indexers frequently cross-link or conflate their original registration numbers (**A339834** and **A364874**) under a single renewal entry.

2. **Revised Editions:**
   *The World of Carbon* was revised and reprinted in subsequent years (most notably the 1962 Collier Books paperback edition). Revised editions often received their own separate original registration numbers to protect the new/revised content. When researchers look up the book, they sometimes find these later registration numbers and mistakenly try to link them to the original 1986 renewal (RE277631), which only legally covers the 1958 original text.

3. **Clerical and OCR Errors:**
   In digitized catalogs of the US Copyright Office, optical character recognition (OCR) errors or manual data-entry typos sometimes swap adjacent registration numbers (e.g., misreading A339834 as A339835).

---

### What is Verified?

From a legal and bibliographical standpoint, the following facts are **verified**:

* **The Original Registration:** *The World of Carbon* (1958 first edition) was successfully registered under number **A339834** on May 9, 1958.
* **The Renewal:** Isaac Asimov timely and legally renewed the copyright for this specific text on **January 16, 1986**, under renewal number **RE277631**.
* **Current Copyright Status:** Because the renewal is valid, the original 1958 text of *The World of Carbon* is **verified to be under copyright protection** in the United States. It will not enter the public domain until 95 years after its publication date (January 1, 2054).

---

### What is Unresolved?

In copyright clearance investigations (such as those conducted by digital libraries), the following details often remain **unresolved** or require manual case-by-case auditing:

* **The Status of Revised Editions (e.g., 1962):**
  While the 1958 text is verified as copyrighted, it is often unresolved whether the *new* material introduced in the 1962 revised edition was ever renewed. If the 1962 edition's unique registration was not renewed in its 28th year (around 1990), the 1962 revisions would technically be in the public domain, even though the core 1958 text remains copyrighted.
* **Database Cleanup:**
  In public databases, the erroneous link between *The World of Carbon's* renewal (RE277631) and *The World of Nitrogen's* original registration (A364874) remains an unresolved data-integrity issue. Human intervention is required to manually decouple these records in volunteer-run copyright registries.

</details>

<details>
<summary><strong>Unedited no-tool baseline 3: 1931–1963 trends</strong></summary>

To understand how the **candidate renewal-linkage share**—the proportion of U.S. Class A (book) registrations that can be successfully matched to a corresponding copyright renewal record—changed from 1931 to 1963, we must look at the intersection of **empirical copyright economics**, **legal history**, and **data science methodology**.

In empirical studies of copyright (such as those utilizing the Stanford Copyright Renewal Database and the New York Public Library’s digitized Catalog of Copyright Entries), the candidate renewal-linkage share serves as a proxy for the actual copyright renewal rate.

The historical trajectory of this share is marked by a gradual rise, punctuated by a **distinct structural break near the registration year 1953**.

---

### 1. The Overall Trend: 1931 to 1963
During the era of the 1909 Copyright Act, works received an initial 28-year term of protection. To extend this protection for a second term, the copyright owner had to file a renewal registration during the 28th year. If they failed to do so, the work entered the public domain.

* **1931–1940s (The Low-Plateau Era):** The candidate renewal-linkage share was remarkably low, hovering between **7% and 10%**. During the Great Depression and World War II, the vast majority of books had short commercial lifespans. Publishers and authors saw little economic value in paying the renewal fee and filing the paperwork, allowing 90%+ of books to enter the public domain.
* **1950s (The Transition):** The linkage share began to climb steadily, passing **12% to 15%**.
* **1960–1963 (The Peak):** By the end of the manual-renewal era (1963 registrations, which were due for renewal in 1991), the linkage share reached its peak at **over 20%**. (Works registered in 1964 and later were granted automatic renewal by Congress in 1992).

---

### 2. Investigating the "Break" Near 1953
When plotting the renewal-linkage share by registration year, researchers observe a noticeable structural break (a shift in the baseline and slope of the curve) around **1953**.

This break is not a random fluctuation; it is driven by two distinct factors: **substantive legal changes** and **technical data transitions**.

#### A. The Substantive Legal Driver: The 1976 Copyright Act
The most significant driver of the break is the **1976 Copyright Act**, which went into effect on **January 1, 1978**.

* **The Math of the 28-Year Term:**
  * Books registered in **1949** came up for renewal in **1977** (under the old 1909 Act rules).
  * Books registered in **1950** came up for renewal in **1978** (the first year of the 1976 Act).
  * Books registered in **1953** came up for renewal in **1981**.
* **The Incentive Shift:** The 1976 Act extended the renewal term from 28 years to **47 years** (bringing total protection to 75 years). This massive extension of the monopoly period dramatically increased the expected future value of a copyright.
* **Why the break peaks/stabilizes near 1953:** While the legal transition occurred in 1978 (affecting 1950 registrations), the publishing industry took a few years to fully react to the new law. By 1981 (the renewal year for 1953 registrations), the economic incentives of the 47-year extension were fully realized, and the commercial value of backlists was rising rapidly due to the paperback boom and the growth of institutional library markets. This caused a sharp, permanent upward shift in the propensity to renew.

#### B. The Technical/Data Artifact Driver: Database Transition
In data science, "linkage" requires matching a registration dataset with a renewal dataset. The break near 1953 registrations (renewed in 1981) corresponds directly to a major transition in how the U.S. Copyright Office recorded data.

* **Pre-1978 Renewals (Registrations before 1950):** These renewals were recorded in physical, printed volumes of the Catalog of Copyright Entries (CCE). To build databases like Stanford's, these physical catalogs had to be digitized via Optical Character Recognition (OCR) or manual keying. OCR errors in names, titles, and registration numbers create "noise," which **lowers the candidate linkage rate** because matching algorithms fail to pair imperfectly digitized records.
* **Post-1978 Renewals (Registrations from 1950 onward, fully stabilizing by 1953/1981):** In 1978, the Copyright Office migrated to a native, machine-readable digital database (the COHM/COHD systems).
* **The Impact on Linkage:** Because renewals filed in 1981 (1953 registrations) exist as clean, structured, native digital data rather than OCR'ed paper scans, the matching algorithms perform significantly better. The "break" near 1953 is partly a **technical artifact**: the candidate renewal-linkage share jumps because the quality of the renewal data suddenly improves, reducing false negatives in the record-linkage process.

### Summary
The break in the candidate renewal-linkage share near 1953 represents a perfect storm of law and data. Legally, it reflects the **heightened economic value of copyright** brought on by the 1976 Act's term extension. Methodologically, it reflects the **transition from dirty OCR data to clean, native digital records** at the U.S. Copyright Office, which artificially boosts the success rate of modern database-matching algorithms.

</details>

## Evaluation and what remains uncertain

Five live scenarios were exercised: **renewed work**, **missing/unresolved renewal**, **conflicting references**, **ambiguous input requiring clarification**, and **cross-year SQL analysis**. Their structural checks confirmed, among other things, that citations resolve to available evidence IDs, tools are attributed to agents, and clarification can occur without dispatching Researchers. **Structural PASS is not a legal or factual correctness certificate**; the reports were also reviewed for unsupported negative-search statements, unverified conflict resolution, wrong SQL class boundaries, and unit-of-analysis errors. Several of those issues led to the implemented source and cohort guards.

The project intentionally **does not** claim that lack of a renewal hit proves the public domain. For example, *The Price of Salt* (1952; Claire Morgan/Patricia Highsmith; registration `A68131`) remained **undetermined** after searches under the original title, later title *Carol*, and the author/pseudonym. This is a useful fourth test case for the grader, but not a substitute for the three cases above.

Further research limits: OCR/transcription gaps; unverified historical source documents; registration versus publication-date ambiguity; identity/edition ambiguity; potentially restored foreign copyright (URAA); separate protection for translations or revised matter; and the difference between an item being digitized or borrowable and being legally reusable. **The 1953 break is an observed feature of the loaded transcript, not an established historical causal claim.**

## Run locally

Requirements: Python and [`uv`](https://docs.astral.sh/uv/), the prepared `data/reg_status_*.parquet` and `data/renewals.parquet` files, and Google Cloud Application Default Credentials with access to the configured Vertex AI Gemini models. The repository root contains `app.py`, `pyproject.toml`, and `uv.lock`.

```bash
uv sync
gcloud auth application-default login
uv run app.py
```

Open `http://localhost:8000`. Use the three example-mode cards or enter your own question. For a direct request to the grader-facing API:

```bash
curl -s http://localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Is Strangers on a Train by Patricia Highsmith (1950) in the public domain in the United States?"}'
```

The JSON response contains `response`, `session_id`, `needs_clarification`, `tool_calls` (including `agent` for each call), `rounds`, `researchers`, and cited `evidence`. The web UI streams research progress and keeps the full technical evidence log and research rounds available on demand.

Selected checks (run in the repository root):

```bash
uv run python -m unittest discover -s tests -p 'test_final_polish.py' -v
uv run python -m unittest discover -s tests -p 'test_milestone45.py' -v
uv run python -m unittest discover -s tests -p 'test_quality_guard.py' -v
uv run python tests/test_pipeline.py
```

Live evaluation (requires the server running; invokes the model and may incur usage costs):

```bash
uv run python scripts/evaluate_live.py --case renewed
uv run python scripts/evaluate_live.py --case variants
uv run python scripts/evaluate_live.py --case patterns
```

## Deployment and submission

Deploy the FastAPI service to **Google Cloud Run**, ideally using continuous deployment from GitHub as required by the course. Include the prepared Parquet data in the image or make them available from cloud storage at startup; grant the service account the required Vertex AI permissions. Configure an appropriate Cloud Run request timeout (the course graders may wait up to five minutes per answer). Check the public root page, `/healthz`, and `/chat` from outside your local machine before submitting.

At the repository root, submit:

```text
app.py                  # API and web server
index.html              # user-facing research interface
research.py             # Lead / Researchers / Writer
records.py              # historical and external evidence tools
cohort_research.py      # validated annual Class A SQL research
pyproject.toml
uv.lock
README.md
submission.json         # deploy_url, authors (every team member), path="research"
```

**Before submission:** replace `submission.json`'s placeholder `deploy_url` with the reachable Cloud Run address and ensure `authors` lists every team member's UNI/email. The code and tests described above were validated locally; **Cloud Run deployment is not claimed as complete here; the same-model, no-tool baseline has been run and recorded above.**

---

*Historical copyright research is valuable precisely because an attractive answer is not enough. What matters is being able to show which records support it, which apparently relevant records do not, and where the evidence ends.*
