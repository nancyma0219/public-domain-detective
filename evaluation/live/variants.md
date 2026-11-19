# variants

**Question:** Investigate the 1958 U.S. copyright registration and renewals for Isaac Asimov's The World of Carbon. Explain any conflicting original registration numbers or dates and whether the renewal records refer to the same edition.
**Time:** 44.79 s | **Rounds:** 2 | **Researchers:** 4

## Automatic structural checks

- PASS: no_server_error
- PASS: has_response
- PASS: all_bracket_citations_in_evidence
- PASS: all_tool_calls_tagged_with_agent
- PASS: not_clarification
- PASS: researchers_launched
- PASS: writer_and_citation_check
- PASS: ran_followup_round

## Final answer

**Verdict:** In copyright in the U.S. until January 1, 2054 [RULE:1958-us-True].

**Confidence:** High, because the 1958 original registration was successfully renewed within the statutory window, and all conflicting registration dates and edition links have been fully reconciled.

### Evidence
- *The World of Carbon* by Isaac Asimov was first published in 1958 [OL:OL46380W].
- The domestic U.S. edition was registered on August 22, 1958, as registration A352575 [REG:14A88E33-72C4-1014-84F6-87703AD4166D].
- An ad interim registration for the London edition was recorded under number AI5926, which contains a clerical transcription date of April 1, 1953, in original registration databases [SQL:3c37f408].
- On January 6, 1986, the work was renewed under RE277631, linking both the domestic registration A352575 (dated August 22, 1958) and the ad interim registration AI5926 (correctly listed in the renewal record with its true original date of April 1, 1958) [SQL:884945fc].
- A separate, revised edition of the book was registered on March 28, 1962, under registration A557886 [SQL:3c37f408] and renewed on April 5, 1990, under RE476868 [REN:RE476868].
- Author Isaac Asimov lived from January 2, 1920, to April 6, 1992 [OL:AUTHOR:OL34221A].

### What these records can't tell us
- The original registration database lists the date for the ad interim registration AI5926 as April 1, 1953, rather than the correct date of April 1, 1958. These records cannot tell us the exact cause of this transcription/OCR error, though it is corrected in the 1986 renewal filing.
- The registration and renewal databases only provide metadata and cannot show the physical text of the 1962 revised edition to reveal which specific parts of the book are new material.

### Digitized copies and access
- **HathiTrust:** No matching copy found in HathiTrust in this search.
- **Project Gutenberg:** No matching copy found in Project Gutenberg in this search.
- **Open Library:** A borrowable ebook of the work is available under ID [OL:OL46380W].

_Not legal advice. Records: NYPL Catalog of Copyright Entries transcriptions._

### Sources
- `RULE:1958-us-True` U.S. Copyright Office Circular 15A (Duration) and Circular 22 (How to Investigate the Copyright Status of a Work), https://www.copyright.gov/circs/circ22.pdf
- `OL:OL46380W` Open Library — https://openlibrary.org/works/OL46380W
- `REG:14A88E33-72C4-1014-84F6-87703AD4166D` NYPL Catalog of Copyright Entries — registrations (github.com/NYPL/catalog_of_copyright_entries_project)
- `SQL:3c37f408` Query over the NYPL CCE registration and renewal tables
- `SQL:884945fc` Query over the NYPL CCE registration and renewal tables
- `REN:RE476868` NYPL CCE renewals (github.com/NYPL/cce-renewals)
- `OL:AUTHOR:OL34221A` Open Library Authors API — https://openlibrary.org/authors/OL34221A

## Manual review needed

- Confirm facts, citations, original registration and renewal keys against source rows
- Check response directly answers the user question and explains uncertainty
- Check whether follow-up investigation was justified, not simply longer
- Check digital availability assertions are source-scoped

**Note:** A passing structural check is not legal verification or factual correctness.