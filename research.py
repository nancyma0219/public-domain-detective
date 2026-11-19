"""The deep-research pipeline: a Lead that clarifies and plans, Researchers that run in parallel in
fresh contexts, and a Writer whose citations are checked in code.

    user question
        -> Lead: vague?  -> "CLARIFY: ..." (returned to the user, nothing else runs)
                 else    -> dispatch_researchers([task, task, ...])   # one call, run with asyncio.gather
                            ... findings come back; a gap? dispatch again (MAX_ROUNDS in code)
                         -> "BRIEF: ..."
        -> Writer: report citing evidence ids [REG:...] [REN:...]
        -> citation check (code): unknown ids or uncited evidence bullets -> one revision, then strip
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Callable

from agents import Agent, ModelSettings, RunContextWrapper, Runner, function_tool
from agents.extensions.models.litellm_model import LitellmModel

import records
from gap_review import review_round
from citation_guard import verify_citation_facts
from report_guard import verify_report_claims
from quality_guard import question_mode, check_research_claims
import cohort_research
import evidence_verification
from context_panel import AgentContexts, PanelHooks

# LiteLLM routes the call to Gemini on Vertex AI; api_key is unused (gcloud credentials are).
LEAD_MODEL = LitellmModel(model="vertex_ai/gemini-3.5-flash", api_key="unused")
RESEARCHER_MODEL = LitellmModel(model="vertex_ai/gemini-3.5-flash-lite", api_key="unused")
WRITER_MODEL = LitellmModel(model="vertex_ai/gemini-3.5-flash", api_key="unused")
SETTINGS = ModelSettings(extra_args={"vertex_location": "global", "timeout": 90, "num_retries": 2})

MAX_ROUNDS = 2          # the Lead may go back for more once after the first fan-out
MAX_PER_ROUND = 4       # researchers per round
RESEARCHER_TURNS = 12
LEAD_TURNS = 10
TOOL_OUTPUT_CHARS = 6000


# --- Per-question state, shared by every agent through the run context -------------------------


@dataclass
class Investigation:
    question: str
    emit: Callable[[dict], None] = lambda event: None
    contexts: AgentContexts = field(default_factory=AgentContexts)
    ledger: dict[str, dict] = field(default_factory=dict)   # evidence id -> {source, summary, url}
    tool_calls: list[dict] = field(default_factory=list)    # the /chat "tool_calls", every agent's
    rounds: int = 0
    researchers: int = 0
    findings: list[dict] = field(default_factory=list)      # {agent, task, report}
    hooks: "RecordingHooks" = None

    def __post_init__(self):
        self.hooks = RecordingHooks(self)


class RecordingHooks(PanelHooks):
    """The context panel's hooks, plus: record every tool call (with its agent) and every evidence id
    a tool returned, so the Writer's citations can be checked against what was really seen."""

    def __init__(self, inv: Investigation):
        super().__init__(inv.contexts, inv.emit)
        self.inv = inv

    async def on_tool_end(self, context, agent, tool, result):
        args = getattr(context, "tool_arguments", None)
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except ValueError:
            pass
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        self.inv.tool_calls.append({"agent": agent.name, "name": tool.name, "arguments": args,
                                    "output": text[:14000] + ("..." if len(text) > 14000 else "")})
        try:
            register_evidence(self.inv, tool.name, json.loads(text))
        except ValueError:
            pass
        self.activity(agent.name, f"{tool.name} → {_brief(text)}")


def _brief(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return text[:80]
    if data.get("status") in ("source_unavailable", "error"):
        err = data.get("error")
        return f"{data['status']}: {str(err)[:80]}"
    if data.get("status") == "no_results":
        return "0 results (search-specific; not proof of absence)"
    for key in ("results", "items", "rows"):
        if key in data:
            return f"{len(data[key])} {key}"
    return data.get("verdict", "ok")


def register_evidence(inv: Investigation, tool: str, data) -> None:
    """Walk a tool result; every dict with an 'eid' becomes a citable piece of evidence."""
    if isinstance(data, list):
        for d in data:
            register_evidence(inv, tool, d)
        return
    if not isinstance(data, dict):
        return
    if data.get("eid"):
        eid = data["eid"]
        entry = inv.ledger.setdefault(eid, {
            "tool": tool, "url": data.get("url"), "summary": _summarize(data),
            "record_type": eid.split(":", 1)[0], "record": dict(data),
            "source": data.get("source") or SOURCE_OF.get(eid.split(":")[0], tool)})
        # A renewal ID can appear with different original registration numbers/dates.
        # Do not silently collapse those associations in the citation evidence ledger.
        if eid.startswith("REN:"):
            # Registration search can pre-populate a synthetic REN stub. Prefer
            # the subsequently retrieved actual renewal row for factual checking.
            if (data.get("orig_regnum") or data.get("original_regnum")) and                not (entry.get("record") or {}).get("orig_regnum"):
                entry["record"] = dict(data)
                entry["summary"] = _summarize(data)
                entry["tool"] = tool
            variants = entry.setdefault("variants", [])
            key_fields = ("orig_regnum", "original_regnum", "orig_regdate", "original_regdate", "source_file")
            variant = {k: data.get(k) for k in key_fields if data.get(k) is not None}
            if variant and variant not in variants:
                variants.append(variant)
            if len({(v.get("orig_regnum") or v.get("original_regnum"),
                     v.get("orig_regdate") or v.get("original_regdate")) for v in variants}) > 1:
                entry["ambiguous_original_key"] = True
                entry["summary"] = (f"Renewal {eid} has conflicting original-registration references: "
                                    + "; ".join(str(v) for v in variants)[:420]
                                    + ". Check source rows; do not cite this ID as a unique linkage.")
    if data.get("renewal_eid"):
        inv.ledger.setdefault(data["renewal_eid"], {
            "tool": tool, "url": None, "source": SOURCE_OF["REN"],
            "record_type": "REN", "record": {"renewal_id": data.get("renewal_id"),
            "renewal_date": data.get("renewal_date"), "original_regnum": data.get("regnum"),
            "original_regdate": data.get("regdate")},
            "summary": f"Renewal {data.get('renewal_id')} filed {data.get('renewal_date')} by "
                       f"{data.get('renewal_claimants')}, for registration {data.get('regnum')} of {data.get('regdate')}"})
    for v in data.values():
        if isinstance(v, (list, dict)):
            register_evidence(inv, tool, v)


SOURCE_OF = {
    "REG": "NYPL Catalog of Copyright Entries — registrations (github.com/NYPL/catalog_of_copyright_entries_project)",
    "REN": "NYPL CCE renewals (github.com/NYPL/cce-renewals)",
    "SQL": "Query over the NYPL CCE registration and renewal tables",
    "RULE": "U.S. Copyright Office Circulars 15A and 22, applied as code",
    "OL": "Open Library", "HT": "HathiTrust Bibliographic API", "WD": "Wikidata", "PG": "Project Gutenberg",
}


def _summarize(d: dict) -> str:
    skip = {"eid", "url", "source", "entry_id", "match_score", "renewal_eid", "reasoning"}
    parts = [f"{k}={v}" for k, v in d.items() if k not in skip and v not in (None, "", []) and not isinstance(v, (dict,))]
    if d.get("reasoning"):
        parts.append("reasoning=" + " | ".join(d["reasoning"]))
    return "; ".join(parts)[:600]


def _out(data) -> str:
    text = json.dumps(data, default=str, ensure_ascii=False)
    return text if len(text) <= TOOL_OUTPUT_CHARS else text[:TOOL_OUTPUT_CHARS] + ' ..."[truncated]"'


# --- Researcher tools (sync: the SDK runs them in worker threads, so they run in parallel) -------


@function_tool
def search_registrations(title: str, author: str | None = None, year_from: int | None = None,
                         year_to: int | None = None) -> str:
    """Fuzzy-search the 1923-1969 Catalog of Copyright Entries registrations. Each hit includes the
    renewal matched to it by registration number and date (renewal_id null = none matched).

    Args:
        title: Book title, or its distinctive words.
        author: Author name, optional.
        year_from: Earliest registration year, optional.
        year_to: Latest registration year, optional.
    """
    return _out(records.safe(records.search_registrations, title=title, author=author,
                             year_from=year_from, year_to=year_to))


@function_tool
def search_renewals(title: str, author: str | None = None) -> str:
    """Search renewal records directly by title and author. Use it even when search_registrations
    found no matched renewal: a renewal can cite a mistyped registration number or date.

    Args:
        title: Book title.
        author: Author or renewal claimant name, optional.
    """
    return _out(records.safe(records.search_renewals, title=title, author=author))


@function_tool
def verify_record_link(registration_entry_id: str) -> str:
    """Inspect a registration's number+date against renewal records, preserving individual
    evidence IDs and sources. A candidate link never proves legal copyright status.

    Args:
        registration_entry_id: The entry_id field returned by search_registrations (without REG:).
    """
    return _out(records.safe(evidence_verification.verify_record_link,
                             registration_entry_id=registration_entry_id))


@function_tool
def query_records(sql: str) -> str:
    """Run one read-only DuckDB SELECT over the tables reg_status and renewals, for counts,
    rates and patterns across authors, publishers or years. Returns at most 50 rows.

    Args:
        sql: A single SELECT statement.
    """
    return _out(records.query_records(sql))


query_records.description += "\n\nSchema:\n" + records.SCHEMA


@function_tool
def check_us_status(pub_year: int, published_in_us: bool, had_notice: bool | None = True,
                    renewed: bool | None = None, renewal_year: int | None = None,
                    author_death_year: int | None = None) -> str:
    """Apply the U.S. copyright term rules (Copyright Office Circulars 15A and 22) as code. Never
    decide the status yourself: gather the facts, then call this.

    Args:
        pub_year: Year of first publication.
        published_in_us: False if first published abroad (then the 1996 URAA restoration may apply).
        had_notice: Whether it was published with a copyright notice (true for registered books).
        renewed: True if a renewal was found, False if searched and none found, null if not searched.
        renewal_year: Year of the renewal, if found.
        author_death_year: Author's death year, if known (matters for foreign works).
    """
    return _out(records.us_status(pub_year=pub_year, published_in_us=published_in_us, had_notice=had_notice,
                                  renewed=renewed, renewal_year=renewal_year, author_death_year=author_death_year))


@function_tool
def openlibrary_search(title: str, author: str | None = None) -> str:
    """Open Library: editions, first publication year, publishers, places, and OCLC/LCCN numbers
    (which hathitrust_lookup needs).

    Args:
        title: Book title.
        author: Author, optional.
    """
    return _out(records.safe(records.openlibrary_search, title=title, author=author))


@function_tool
def openlibrary_author(name: str) -> str:
    """Open Library Authors API: author identity candidates, aliases/pseudonyms, and birth/death
    dates if supplied. Duplicate names can represent distinct records; do NOT merge or silently
    choose the first. This source does not establish citizenship or publication country.

    Args:
        name: Author name or pseudonym.
    """
    return _out(records.safe(records.openlibrary_author, name=name))


@function_tool
def hathitrust_lookup(oclc: str | None = None, lccn: str | None = None) -> str:
    """HathiTrust's rights code for scanned copies of a book (pd = public domain, ic = in copyright,
    und = undetermined) and full-view links. Needs an OCLC or LCCN number.

    Args:
        oclc: OCLC number.
        lccn: Library of Congress control number.
    """
    return _out(records.safe(records.hathitrust_lookup, oclc=oclc, lccn=lccn))


@function_tool
def wikidata_author(name: str) -> str:
    """Wikidata facts about an author: citizenship, birth and death years. Use it to tell whether a
    work is foreign (URAA) and for life+70 reasoning.

    Args:
        name: The author's name.
    """
    return _out(records.safe(records.wikidata_author, name=name))


@function_tool
def gutenberg_search(title: str, author: str | None = None) -> str:
    """Is there a free Project Gutenberg e-text of this book?

    Args:
        title: Book title.
        author: Author, optional.
    """
    return _out(records.safe(records.gutenberg_search, title=title, author=author))


researcher = Agent(
    name="Researcher",
    instructions=f"""\
You are a copyright-records researcher. You get one task from the Lead, in a fresh context. Use
your tools to establish facts; never answer from memory.

Ground rules:
- Search well before concluding something is missing: try the short distinctive title words, with and
  without the author, and search_renewals as well as search_registrations. Note OCR and date mismatches.
- The same renewal ID can refer to multiple original registration keys in the transcribed database.
  Keep each original number/date association distinct; compare it with the actual registration.
  Do NOT present a renewal ID alone as proof that a particular original edition was renewed.
  Use verify_record_link for an original registration when available; if conflicting, report both
  keys and say that the original source record requires checking.
- A registration's regnum prefix tells you the class: A = U.S. book, AF/AFO = foreign or
  foreign-language book, AI = ad interim (English-language book first published abroad).
- If you are asked for a status, call check_us_status with the facts you found.
- For external APIs, read `status`: success, no_results, source_unavailable, or error. A 403
  is source_unavailable, NOT zero matches. Never infer that a work is unavailable or unrenewed
  because a remote service failed. Use openlibrary_author to investigate dates and pseudonyms, but Open Library can return
  multiple author IDs for the same name. Compare aliases with the named work; cite the specific
  author candidate ID [OL:AUTHOR:...] and flag unresolved identity. The author API does not provide
  independently verified citizenship or first-publication country.
- For aggregate/year-by-year U.S. book questions, independently verify SQL cohort eligibility:
  use regexp_matches(regnum, '^A[0-9]') for exact domestic Class A (never all rows or LIKE 'A%');
  compute candidate linkage counts (renewal_id IS NOT NULL), not a verified legal renewal rate.
  If asked to explain a discontinuity, execute a separate provenance/denominator diagnostic SQL
  (e.g., counts by source_file or catalog_year and duplicate identifiers); avoid causal claims
  when no comparison establishes the mechanism. Do not silently count multiple rows as works.
- Respect the Lead's source assignment: Records tasks use NYPL tools first; Bibliography
  tasks use Open Library book and author searches first; Access tasks use HathiTrust/Gutenberg first.
  If HathiTrust needs an OCLC/LCCN, obtain it from Open Library and call HathiTrust;
  report 'identifier unavailable' if none can be obtained. Do not silently omit a source.
- When Project Gutenberg returns no_results, write 'not found in this Gutenberg search',
  not 'no free editions exist'. Report all API failures in your Gaps section.

Reply with a short findings report, max ~12 lines:
- One line per fact, each ending with the evidence id(s) from tool output in square brackets,
  e.g. "Registered 15 Mar 1950 as A41904 by Harper [REG:A41904@1950-03-15]". Copy ids exactly.
- Then a line starting "Gaps:" listing what you could not establish.""",
    model=RESEARCHER_MODEL,
    model_settings=SETTINGS,
    tools=[search_registrations, search_renewals, verify_record_link, query_records, check_us_status,
           openlibrary_search, openlibrary_author, hathitrust_lookup, gutenberg_search],
)


# --- The Lead's fan-out tool ---------------------------------------------------------------------


@function_tool
async def dispatch_researchers(ctx: RunContextWrapper[Investigation], tasks: list[str]) -> str:
    """Start several Researchers at once. They run in parallel, each in a fresh context that holds
    only its task, and this returns all their findings when every one has finished.

    Args:
        tasks: One self-contained task per Researcher (2-4). Name the book, author, years and exactly
            which records or sources to check.
    """
    inv = ctx.context
    if inv.rounds >= MAX_ROUNDS:
        return (f"Round cap reached ({MAX_ROUNDS} rounds). Do not dispatch again: reply with your BRIEF now, "
                "and list what is still unknown as gaps.")
    inv.rounds += 1
    call_start = len(inv.tool_calls)
    tasks = [t for t in tasks if t.strip()][:MAX_PER_ROUND]
    inv.emit({"type": "round", "round": inv.rounds, "tasks": tasks})

    async def one(task: str):
        inv.researchers += 1
        agent = researcher.clone(name=f"Researcher {inv.researchers}")
        try:
            result = await Runner.run(agent, task, context=inv, hooks=inv.hooks, max_turns=RESEARCHER_TURNS)
            report = str(result.final_output)
        except Exception as e:
            report = f"FAILED: {type(e).__name__}: {str(e)[:300]}"
        inv.findings.append({"agent": agent.name, "round": inv.rounds, "task": task, "report": report})
        return agent.name, task, report

    done = await asyncio.gather(*(one(t) for t in tasks))
    review = review_round(inv.tool_calls[call_start:], round_no=inv.rounds, max_rounds=MAX_ROUNDS, mode=question_mode(inv.question))
    inv.tool_calls.append({"agent": "GapReview", "name": "review_research_gaps",
                           "arguments": {"round": inv.rounds}, "output": json.dumps(review)})
    inv.emit({"type": "activity", "agent": "Lead",
              "text": f"Round {inv.rounds} gap review: {review['actionable_issue_count']} actionable issue(s)"})
    return ("\n\n".join(f"## {name} (round {inv.rounds})\nTask: {task}\n{report}" for name, task, report in done)
            + f"\n\n(Round {inv.rounds} of {MAX_ROUNDS}.)\n"
            + "\n## Evidence-gap review (automated, not a legal conclusion)\n"
            + json.dumps(review, ensure_ascii=False))


lead = Agent(
    name="Lead",
    instructions=f"""\
You lead an investigation into the U.S. copyright status of books, especially books first published
1931-1963, when a copyright had to be renewed in its 28th year or it ended. Researchers do the
record searches; you decide what to look for.

1. Is the question answerable? Reply with "CLARIFY: " and ONE short question (offer 2-3 concrete
   options) and nothing else if:
   - no specific book (title) or well-defined set (an author, a publisher, a year range) is named, e.g.
     "is my grandmother's old novel free to use?", "which old books can I use?";
   - the title is ambiguous between works or editions that matter (an original vs. a later revised
     edition or a translation) and the question does not say which.
   Do not ask about things the Researchers can look up (dates, publishers, nationality).
   If the question is outside these records (music, films, unpublished letters, other countries' law),
   reply "BRIEF: OUT OF SCOPE" and say what these records can and cannot answer.

2. Otherwise call dispatch_researchers ONCE with 2-4 complementary tasks, so they run in parallel:
   - Records: find the registration and any renewal (search_registrations AND search_renewals).
   - Bibliography & author: first publication year/place, editions, pseudonyms and author death year
     (openlibrary_search, openlibrary_author). Do not infer nationality from author's name.
   - Access: HathiTrust rights code and free copies (hathitrust_lookup via an OCLC/LCCN from Open
     Library, gutenberg_search).
   - For questions about patterns across many books: assign complementary SQL analysis tasks,
     specifically cohort counts/trends and independent validity checks. Do not ask for a
     single-book registration/renewal lookup or digital copies unless relevant. Use exact Class A
     regexp_matches(regnum, '^A[0-9]') and call the result a candidate linkage rate, not
     the legal renewal rate. Investigate major discontinuities rather than just listing percentages.
   Ask the Records Researcher to call check_us_status once the facts are in.

3. Read the findings AND the automated Evidence-gap review returned by dispatch_researchers.
   If a candidate renewal ID appears with different original registration numbers/dates, do not
   collapse the variants or resolve the discrepancy from an ID match alone.
   The review suggests specific next searches but is not itself evidence. Explicitly decide which gaps
   could change the answer; do not blindly run a second round for an unrelated API error.
   If they leave a gap that matters to the verdict — no registration found,
   registration found but no renewal (search renewals by title and claimant, alternate titles,
   pseudonyms), dates that conflict, possible foreign first publication, unresolved author identity, HathiTrust disagreeing
   with the records — call dispatch_researchers again with targeted tasks. At most {MAX_ROUNDS} rounds.

4. Finish with "BRIEF: " followed by: a short Research decision explaining whether
   you investigated remaining material gaps, and which ones could not be resolved;
   then the verdict check_us_status gave (or why none is possible),
   the key facts with their evidence ids exactly as the Researchers wrote them, conflicts between
   sources, and the gaps that remain.""",
    model=LEAD_MODEL,
    model_settings=SETTINGS,
    tools=[dispatch_researchers],
)


writer = Agent(
    name="Writer",
    instructions="""\
You write the final case report for a reader (a translator, small publisher, teacher or curious
reader) who wants to know whether they may reuse a book in the U.S. Use ONLY the brief, the
findings and the evidence list you are given. Every evidence id you cite must appear in the
evidence list, character for character.

For an INDIVIDUAL BOOK only, use this format (markdown):
**Verdict:** one line — e.g. "Public domain in the U.S. (not renewed)", "In copyright in the U.S. until
the end of 2045", or "Can't be determined from these records".
**Confidence:** high / medium / low, with one clause saying why.

### Evidence
- 3-7 bullets. One fact each, plain words, ending with its evidence id(s) in square brackets,
  e.g. "Harper registered it on 15 Mar 1950 as A41904 [REG:A41904@1950-03-15]".

### What these records can't tell us
- 1-4 bullets: gaps, conflicts, coverage limits (e.g. pamphlet volumes not transcribed, OCR errors,
  foreign-law questions, later editions' new material). If the data can't answer the question, say so
  here plainly. These bullets may be uncited.

### Digitized copies and access
- List only copies actually returned by HathiTrust / Project Gutenberg / Open Library, with source ids.
- For zero results say "No matching copy found in [named catalog] in this search", NOT "None found", "no free copies exist", or "not available anywhere".
- If a source was unavailable or was not searched, say that explicitly. Never equate access rights with copyright status.

End with the line: _Not legal advice. Records: NYPL Catalog of Copyright Entries transcriptions._

For a pattern/aggregate question, do NOT write a book copyright **Verdict** or **Confidence**.
Instead use: ### Research findings (quantitative trends, salient breaks, and grounded hypotheses),
### Methodology (precise cohort, denominator, numerator, SQL provenance),
### Data limitations (linkage uncertainty, transcription coverage, duplicates, limitations of
inference). Avoid digitized-copies section unless the question asks about access. Use exact
Class A filter regexp_matches(regnum, '^A[0-9]'), not regnum LIKE 'A%' which includes AF/AI.
Call any derived matched percentage a candidate linkage rate, NOT an observed legal renewal rate.
Do not label records outside 1923–1969 corrupted without accounting for 1970–1977 volumes.
Distinguish duplicated registration NUMBER groups from ROW counts.
For questions primarily asking to COMPARE, RECONCILE, or EXPLAIN competing registration,
renewal, or edition records, distinguish two outcomes explicitly:
- First write **Record assessment:** confirmed links, contradictory dates/keys, and which
  discrepancies remain unresolved. Put this before the legal-status line.
- Then write **Verdict:** ONLY as a separate assessment of U.S. copyright status if the
  evidence supports one. A proven domestic registration-to-renewal link can support a
  status conclusion even while a different ad-interim registration's date remains in doubt.
- Treat any asserted transcription error as a hypothesis unless an authoritative original
  record independently establishes the correct entry. Do not describe a case as fully
  reconciled merely because one edition has a matching renewal.
- Use separate confidence language for legal status and record reconciliation; never
  treat confidence in one as confidence in the other.
For individual-book questions, retain the copyright verdict format. Never invent a fact, date, number or id. A missing renewal search hit does not establish public domain.
If source evidence is insufficient, use the verdict "Cannot determine from available records".
Distinguish a renewal not found by a specific search from independently demonstrated non-renewal.
When candidate renewal records have different original registration numbers/dates, describe those
as distinct candidate links and explain which key matches the target registration. A renewal ID
alone is not proof of an edition match. Do not misstate how many independent renewals exist.
If a source returned an error, do not treat it as a negative lookup. Do not invent a URL or a legal clearance.""",
    model=WRITER_MODEL,
    model_settings=SETTINGS,
)


# --- Citation check: code, not a model ---------------------------------------------------------

CITE = re.compile(r"\[((?:REG|REN|SQL|RULE|OL|HT|WD|PG):[^\]\s,;]+)\]")
CITE_GROUP = re.compile(r"\[([A-Z]+:[^\]]+)\]")


def cited_ids(text: str) -> list[str]:
    ids = []
    for group in CITE_GROUP.findall(text):
        ids += [p.strip() for p in re.split(r"[,;]\s*", group) if ":" in p]
    return ids


def check_citations(report: str, ledger: dict, mode: str = "book") -> list[str]:
    problems = []
    for eid in cited_ids(report):
        if eid not in ledger:
            problems.append(f'Cited id "{eid}" is not in the evidence list: use an exact id or drop the claim.')
    section = re.search(r"### Evidence\n(.*?)(\n### |\Z)", report, re.S)
    if section:
        for line in section.group(1).splitlines():
            if line.lstrip().startswith(("- ", "* ", "|")) and not cited_ids(line) and "---" not in line:
                problems.append(f'Uncited evidence line: "{line.strip()[:120]}" -> cite its id or cut it.')
    if mode == "book" and "**Verdict:**" not in report:
        problems.append("Missing the **Verdict:** line.")
    if mode == "aggregate" and "### Research findings" not in report:
        problems.append("Aggregate analysis requires a ### Research findings section.")
    problems.extend(verify_citation_facts(report, ledger))
    problems.extend(verify_report_claims(report, ledger))
    return problems


def strip_unknown(report: str, ledger: dict) -> str:
    def fix(m):
        keep = [p.strip() for p in re.split(r"[,;]\s*", m.group(1)) if p.strip() in ledger]
        return f"[{', '.join(keep)}]" if keep else ""
    return CITE_GROUP.sub(fix, report)


def sources_section(report: str, ledger: dict) -> str:
    lines = []
    for eid in dict.fromkeys(cited_ids(report)):
        ev = ledger.get(eid)
        if not ev:
            continue
        link = f" — {ev['url']}" if ev.get("url") else ""
        lines.append(f"- `{eid}` {ev['source']}{link}")
    return ("\n\n### Sources\n" + "\n".join(lines)) if lines else ""


# --- The whole pipeline --------------------------------------------------------------------------


async def investigate(question: str, history: list[dict], emit: Callable[[dict], None] = lambda e: None,
                      contexts: AgentContexts | None = None) -> dict:
    """Run one question through Lead -> Researchers -> Writer. history: earlier turns of this chat
    ({role, content}), so a clarification answer reaches the Lead with its question. contexts: where
    the context panel should read every agent's context from (a fresh one if not given)."""
    inv = Investigation(question=question, emit=emit, contexts=contexts or AgentContexts())
    lead_input = history + [{"role": "user", "content": question}]
    lead_result = await Runner.run(lead, lead_input, context=inv, hooks=inv.hooks, max_turns=LEAD_TURNS)
    lead_out = str(lead_result.final_output).strip()

    if lead_out.upper().startswith("CLARIFY:"):
        return _response(inv, lead_out.split(":", 1)[1].strip(), needs_clarification=True)

    brief = lead_out.split(":", 1)[1].strip() if lead_out.upper().startswith("BRIEF:") else lead_out
    # Certified cohort calculations use fixed SQL independent of model-generated queries.
    # Keep the parallel Researchers and their trace, but never publish an unvalidated
    # model-computed percentage when a deterministic database result is available.
    cohort = None
    if question_mode(question) == 'aggregate' and cohort_research.is_annual_book_query(question):
        cohort = cohort_research.compute(records.query_records)
        if cohort.get('ok'):
            for item in cohort['queries'].values():
                register_evidence(inv, 'query_records', item)
                inv.tool_calls.append({'agent': 'CohortAudit', 'name': 'query_records',
                    'arguments': {'sql': item['sql']}, 'output': json.dumps(item)})
            emit({'type': 'activity', 'agent': 'CohortAudit',
                  'text': 'Validated annual Class A cohort, two period totals, and 1951–1954 source coverage'})
        else:
            inv.tool_calls.append({'agent': 'CohortAudit', 'name': 'validate_cohort',
                'arguments': {}, 'output': json.dumps({'error': cohort.get('error')})})
    evidence = "\n".join(f"[{eid}] ({ev['source']}) {ev['summary']}" for eid, ev in inv.ledger.items()) or "(none)"
    findings = "\n\n".join(f"## {f['agent']}\nTask: {f['task']}\n{f['report']}" for f in inv.findings) or "(none)"
    writer_input = (f"Question (with conversation):\n{_conversation(lead_input)}\n\nLead's brief:\n{brief}\n\n"
                    f"Researcher findings:\n{findings}\n\nEvidence list (the only ids you may cite):\n{evidence}")

    report = str((await Runner.run(writer, writer_input, context=inv, hooks=inv.hooks)).final_output).strip()
    problems = check_citations(report, inv.ledger, mode=question_mode(question)) + check_research_claims(report, inv.tool_calls, question)
    inv.tool_calls.append({"agent": "CitationCheck", "name": "check_citations", "arguments": {"round": 1},
                           "output": "PASS" if not problems else "\n".join(problems)})
    if problems:
        emit({"type": "activity", "agent": "CitationCheck", "text": f"{len(problems)} problem(s): asking Writer to revise"})
        fix = (writer_input + "\n\nYour draft:\n" + report + "\n\nFix these problems and reply with the whole corrected "
               "report:\n" + "\n".join(problems))
        report = str((await Runner.run(writer, fix, context=inv, hooks=inv.hooks)).final_output).strip()
        left = check_citations(report, inv.ledger, mode=question_mode(question)) + check_research_claims(report, inv.tool_calls, question)
        inv.tool_calls.append({"agent": "CitationCheck", "name": "check_citations", "arguments": {"round": 2},
                               "output": "PASS" if not left else "stripped unknown ids:\n" + "\n".join(left)})
        if left:
            # Fail closed: dropping an unknown citation alone would leave an unsupported claim.
            # Return a transparent limitation instead of publishing an unverified verdict.
            if question_mode(question) == 'aggregate':
                report = ("### Research findings\n"
                          "The available queries do not yet establish a defensible cohort-level result. "
                          "Do not interpret the draft percentages as verified historical renewal rates.\n\n"
                          "### Methodology\n"
                          "Recompute the annual domestic Class A cohort using "
                          "`regexp_matches(regnum, '^A[0-9]')`, with explicit row and "
                          "distinct-key denominators and candidate-link counts.\n\n"
                          "### Data limitations\n"
                          "The incomplete or inconsistent query scope and evidence issues "
                          "are listed in the research trace. No numerical finding is certified.\n\n"
                          "_Not legal advice. Records: NYPL Catalog of Copyright Entries transcriptions._")
            else:
                report = ("**Verdict:** Cannot determine from available records\n"
                      "**Confidence:** low — the draft did not pass evidence checks.\n\n"
                      "### Evidence\n"
                      "- The underlying record searches were performed, but the report's claims "
                      "could not be verified against their cited results.\n\n"
                      "### What these records can't tell us\n"
                      "- A verified copyright determination requires reviewing the source records "
                      "and resolving the citation mismatches listed in the investigation trace.\n\n"
                      "### Digitized copies and access\n- No verified free copy established from the available tool results.\n\n"
                      "_Not legal advice. Records: NYPL Catalog of Copyright Entries transcriptions._")
        else:
            report = strip_unknown(report, inv.ledger)
    else:
        emit({"type": "activity", "agent": "CitationCheck", "text": "every citation matches a record a tool returned"})

    if cohort is not None:
        # Data and arithmetic are rendered from fixed, independently checked SQL, not
        # rewritten by the model. An incomplete query gets a transparent limitation.
        report = cohort_research.markdown(cohort)
    return _response(inv, report + sources_section(report, inv.ledger))


def _conversation(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def _response(inv: Investigation, text: str, needs_clarification: bool = False) -> dict:
    return {
        "response": text,
        "needs_clarification": needs_clarification,
        "tool_calls": inv.tool_calls,
        "rounds": inv.rounds,
        "researchers": inv.researchers,
        "evidence": [{"id": k, **v} for k, v in inv.ledger.items()],
    }
