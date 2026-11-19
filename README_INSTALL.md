# Milestone 4.6 — Question-Aware Results & Final UI Polish

This is a focused patch on top of Milestone 4.5. It changes only `index.html` and `research.py`; `cohort_research.py`, databases, and existing API endpoints remain unchanged.

## What's different

- **Investigate a book:** status stamp still answers the copyright question (e.g., `IN COPYRIGHT`).
- **Compare records:** stamp now describes record assessment (`RECORD COMPARISON` or `DISCREPANCY OPEN`), with separate panels for record reconciliation and the independent U.S. copyright conclusion. Classification uses the submitted question, not merely the selected homepage tab.
- **Explore trends:** stamp says `RESEARCH FINDINGS`; the chart moves before the 33-year table, which is collapsed by default for easier reading. The underlying query results remain available by expanding it.
- Original evidence identifiers, source links, raw tool calls, and expandable research steps remain accessible. The raw log is relabeled as a technical evidence log.
- The Writer is instructed to state `**Record assessment:**` before a separate `**Verdict:**` for record-comparison questions and not claim that an unresolved date discrepancy is fully reconciled.

## Install (from your project root)

```bash
cd ~/Desktop/book-copyright-agent
mkdir -p backups tests
cp index.html backups/index_before_m46.html
cp research.py backups/research_before_m46.py
unzip -o ~/Downloads/milestone4_6_final_polish.zip -d /tmp
cp /tmp/milestone4_6_final_polish/index.html .
cp /tmp/milestone4_6_final_polish/research.py .
cp /tmp/milestone4_6_final_polish/tests/test_final_polish.py tests/
```

## Check

```bash
uv run python -m unittest discover -s tests -p 'test_final_polish.py' -v
uv run python -m unittest discover -s tests -p 'test_milestone45.py' -v
uv run python -m unittest discover -s tests -p 'test_quality_guard.py' -v
uv run python tests/test_pipeline.py
```

The new tests invoke `node` for JavaScript syntax and behavior checking; if Node.js is not installed locally, the Node-specific tests need Node installed or can be skipped separately. Existing Python tests are unaffected.

Restart `uv run app.py` and hard-refresh the browser. Try the three homepage modes. For Compare records, the large stamp should no longer read `IN COPYRIGHT`, but the body will retain a copyright verdict when the evidence supports one. For Trends, the chart must precede the collapsed annual table.

## Scope / caveats

This patch improves interpretation and information hierarchy; it does not independently certify the legal conclusions, reconcile AI5926's conflicting dates, or validate the historical cause of the 1953 discontinuity. Neither full browser E2E nor Vertex/Gemini API calls were run in this patch environment.
