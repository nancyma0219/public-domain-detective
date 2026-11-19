# No-tool baseline: same Gemini model

Model: `vertex_ai/gemini-3.5-flash`. Each run received only the question as a user message; no system prompt, tools or data files.

## book

**Question:** Is Strangers on a Train by Patricia Highsmith (1950) in the public domain in the United States?

**Baseline response (unedited):**

**No**, *Strangers on a Train* by Patricia Highsmith (published in 1950) is **not** in the public domain in the United States.

Under U.S. copyright law, works published between 1928 and 1977 are protected for **95 years** from their date of publication, provided that their copyright was properly registered and renewed in its 28th year.

Because the copyright for *Strangers on a Train* was successfully renewed, it remains protected. It is currently scheduled to enter the public domain in the United States on **January 1, 2046**.

Currently, the rights to Patricia Highsmith's works are actively managed and protected by her estate (represented by the Swiss publisher Diogenes Verlag).

## records

**Question:** Why does Isaac Asimov's The World of Carbon have different original registration numbers associated with renewal RE277631? What is verified and unresolved?

**Baseline response (unedited):**

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

## trends

**Question:** For U.S. Class A books registered from 1931 to 1963, how did the candidate renewal-linkage share change by year? Investigate the break near 1953.

**Baseline response (unedited):**

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
