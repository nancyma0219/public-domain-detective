"""The data layer: every source the agent can consult, as plain Python functions.

Each function returns JSON-safe dicts, and every record carries an evidence id (`eid`) such as
`REG:A41904@1950-03-15` or `HT:mdp.39015...`. The Writer may cite only ids that some tool actually
returned in this session, and app.py checks that in code.

Sources
  REG:  NYPL Catalog of Copyright Entries, registrations 1923-1969 (local Parquet, built offline)
  REN:  NYPL CCE renewals 1950-1991+ (local Parquet, built offline)
  SQL:  a read-only aggregate query over those two tables
  RULE: the U.S. term rules from Copyright Office Circular 15A / Circular 22, run as code
  OL:   Open Library search API (editions, first publication year, OCLC/LCCN numbers)
  HT:   HathiTrust Bibliographic API (rights code, reason, full-view scans)
  WD:   Wikidata (author citizenship, birth and death years: foreign-work / URAA checks)
  PG:   Project Gutenberg catalog (free e-texts)
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import os
import re
import threading
import unicodedata
from pathlib import Path

import duckdb
import httpx
from rapidfuzz import fuzz

DATA = Path(__file__).parent / "data"
USER_AGENT = "PublicDomainDetective/0.1 (Columbia IEOR 4570 student project)"
HTTP = httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

STOPWORDS = set("a an the of and or in on to for by with from at as is its into".split())

# --- DuckDB over the offline-built Parquet files -------------------------------------------------

_local = threading.local()  # one connection per thread: DuckDB connections aren't thread-safe


def db() -> duckdb.DuckDBPyConnection:
    con = getattr(_local, "con", None)
    if con is None:
        con = duckdb.connect()
        con.execute(f"CREATE VIEW reg_status AS SELECT * FROM read_parquet('{DATA}/reg_status_*.parquet')")
        con.execute(f"CREATE VIEW renewals AS SELECT * FROM read_parquet('{DATA}/renewals.parquet')")
        _local.con = con
    return con


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _keywords(title: str, n: int = 3) -> list[str]:
    words = [w for w in norm(title).split() if w not in STOPWORDS and len(w) > 1]
    return sorted(set(words), key=len, reverse=True)[:n] or norm(title).split()[:1]


def _surname(author: str | None) -> str | None:
    """'Patricia Highsmith' / 'Highsmith, Patricia' -> 'highsmith'."""
    if not author:
        return None
    if "," in author:
        return norm(author.split(",")[0]).split()[-1] if norm(author.split(",")[0]) else None
    parts = norm(author).split()
    return parts[-1] if parts else None


def _score(title_q: str, author_q: str | None, title: str | None, author: str | None) -> int:
    """Rank candidates for examination; this score is NOT proof of identity or rights.

    Exact normalized titles outrank translations whose titles merely contain the
    original title in parentheses. Token-set similarity alone makes those tie.
    """
    query_title, candidate_title = norm(title_q), norm(title)
    title_similarity = fuzz.token_set_ratio(query_title, candidate_title)
    if not author_q:
        score = title_similarity
    else:
        surname = _surname(author_q)
        author_similarity = fuzz.partial_ratio(surname, norm(author)) if (surname and author) else 60
        score = 0.7 * title_similarity + 0.3 * author_similarity
    if query_title and query_title == candidate_title:
        score += 20  # exact title is stronger than a partial/translated-title match
    elif query_title and candidate_title.startswith(query_title + " "):
        score += 5
    return int(round(score))


def search_registrations(title: str, author: str | None = None, year_from: int | None = None,
                         year_to: int | None = None, limit: int = 8) -> dict:
    """Fuzzy-search registrations; each hit comes with the renewal matched to it offline."""
    where, params = [], []
    for w in _keywords(title):
        where.append("title_norm LIKE ?")
        params.append(f"%{w}%")
    surname = _surname(author)
    if surname:
        # Soft filter: CCE sometimes puts the author in <title>, and lists an author's later works under
        # one heading, so those entries have no author of their own (authors_norm = '').
        where.append("(authors_norm LIKE ? OR title_norm LIKE ? OR authors_norm = '')")
        params += [f"%{surname}%", f"%{surname}%"]
    if year_from:
        where.append("reg_year >= ?")
        params.append(year_from)
    if year_to:
        where.append("reg_year <= ?")
        params.append(year_to)
    # SQL prioritizes exact normalized titles BEFORE the bounded Python ranking stage.
    # The previous unordered LIMIT 400 could exclude the intended title entirely.
    scan_cap = 5000
    params += [norm(title), scan_cap + 1]
    rows = db().execute(f"""
        SELECT regnum, regdate, authors, title, publisher, pubdate, source_file, entry_id,
               renewal_id, renewal_date, renewal_claimants, match_status
        FROM reg_status WHERE {' AND '.join(where) or 'TRUE'}
        ORDER BY CASE WHEN title_norm = ? THEN 0 ELSE 1 END,
                 length(title_norm), entry_id
        LIMIT ?""", params).fetchall()
    scan_truncated = len(rows) > scan_cap
    rows = rows[:scan_cap]
    cols = ["regnum", "regdate", "authors", "title", "publisher", "pubdate", "source_file", "entry_id",
            "renewal_id", "renewal_date", "renewal_claimants", "match_status"]
    hits = [dict(zip(cols, r)) for r in rows]
    for h in hits:
        h["match_score"] = _score(title, author, h["title"], h["authors"])
    hits.sort(key=lambda h: -h["match_score"])
    out = []
    for h in hits[:limit]:
        h["eid"] = f"REG:{h['entry_id']}" if h.get("entry_id") else f"REG:{h['regnum']}@{h['regdate']}"
        h["match_status"] = h.get("match_status", "unverified")
        h["class"] = _reg_class(h["regnum"])
        if h["renewal_id"]:
            h["renewal_eid"] = f"REN:{h['renewal_id']}"
        out.append(h)
    return {
        "source": "NYPL Catalog of Copyright Entries, registrations (book volumes 1923-1969)",
        "query": {"title": title, "author": author, "year_from": year_from, "year_to": year_to},
        "candidates_scanned": len(hits),
        "scan_truncated": scan_truncated,
        "retrieval_note": ("Search examined at most 5000 prioritized candidates; more may exist. "
                           "A missing result does not establish absence of registration."
                           if scan_truncated else "All matches to the applied SQL filters were considered."),
        "results": out,
        "coverage_note": "NYPL catalog transcription is not a complete inventory of every publication. "
                         "A missing registration is not proof that the work was never registered.",
    }


def _reg_class(regnum: str | None) -> str:
    """Registration-number prefix -> what it means (Catalog of Copyright Entries classes)."""
    r = (regnum or "").upper()
    if r.startswith(("AFO", "AF")):
        return "AF: ad interim / foreign-language or foreign-published book"
    if r.startswith("AI"):
        return "AI: ad interim (English-language book first published abroad)"
    if r.startswith("A"):
        return "A: book published in the U.S."
    if r.startswith("B"):
        return "B: periodical contribution / pamphlet"
    return "unknown class"


def search_renewals(title: str, author: str | None = None, limit: int = 8) -> dict:
    """Search renewal records directly by title/author, which also catches renewals whose original
    registration number was mistyped or never transcribed (so the offline join missed them)."""
    where, params = [], []
    for w in _keywords(title):
        where.append("title_norm LIKE ?")
        params.append(f"%{w}%")
    surname = _surname(author)
    if surname:
        where.append("(author_norm LIKE ? OR claimants ILIKE ?)")
        params += [f"%{surname}%", f"%{surname}%"]
    scan_cap = 5000
    params += [norm(title), scan_cap + 1]
    rows = db().execute(f"""
        SELECT id, rdat, oreg, odat, author, title, claimants, new_matter, notes, source_file
        FROM renewals WHERE {' AND '.join(where) or 'TRUE'}
        ORDER BY CASE WHEN title_norm = ? THEN 0 ELSE 1 END,
                 length(title_norm), entry_id
        LIMIT ?""", params).fetchall()
    scan_truncated = len(rows) > scan_cap
    rows = rows[:scan_cap]
    cols = ["renewal_id", "renewal_date", "orig_regnum", "orig_regdate", "author", "title", "claimants",
            "new_matter", "notes", "source_file"]
    hits = [dict(zip(cols, r)) for r in rows]
    for h in hits:
        h["match_score"] = _score(title, author, h["title"], h["author"] or h["claimants"])
    hits.sort(key=lambda h: -h["match_score"])
    out = []
    for h in hits[:limit]:
        h["eid"] = f"REN:{h['renewal_id']}"
        out.append(h)
    return {
        "source": "NYPL CCE renewals (Catalog of Copyright Entries 1950-1977 + Copyright Office database 1978+)",
        "query": {"title": title, "author": author},
        "candidates_scanned": len(hits),
        "scan_truncated": scan_truncated,
        "retrieval_note": ("Search examined at most 5000 prioritized candidates; additional records may exist. "
                           "Do not infer absence of renewal."
                           if scan_truncated else "All matches to the applied SQL filters were considered."),
        "results": out,
        "coverage_note": "No search hit does NOT prove non-renewal. Coverage gaps, transcription errors, "
                         "title variants, and unmatched dates require additional investigation.",
    }


READ_ONLY = re.compile(r"^\s*(with|select)\b", re.I)
FORBIDDEN = re.compile(r"\b(attach|copy|install|load|pragma|create|insert|update|delete|drop|alter|export|"
                       r"read_csv|read_parquet|read_json|glob|httpfs|set)\b", re.I)


def query_records(sql: str, max_rows: int = 50) -> dict:
    """Read-only SQL over the views reg_status and renewals (aggregate / pattern questions)."""
    if not READ_ONLY.match(sql) or FORBIDDEN.search(sql) or ";" in sql.strip().rstrip(";"):
        return {"error": "Only a single read-only SELECT over reg_status and renewals is allowed."}
    try:
        cur = db().execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    except Exception as e:  # the model can't see exceptions: return something it can fix
        return {"error": f"{type(e).__name__}: {str(e)[:400]}"}
    eid = "SQL:" + hashlib.sha1(sql.encode()).hexdigest()[:8]
    return {
        "eid": eid,
        "sql": sql,
        "columns": cols,
        "rows": [list(map(_jsonable, r)) for r in rows[:max_rows]],
        "truncated": len(rows) > max_rows,
    }


def _jsonable(v):
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)


SCHEMA = """\
reg_status (one row per registration, 1923-1969 book volumes, renewal joined on regnum+regdate):
  regnum, regdate (YYYY-MM-DD), reg_year INT, authors, title, publisher, pubdate,
  title_norm, authors_norm (lowercase, punctuation stripped), source_file, entry_id,
  renewal_id (NULL = no renewal matched), renewal_date, renewal_claimants
  regnum prefix: 'A' = U.S. book, 'AF'/'AFO' = foreign/foreign-language book, 'AI' = ad interim, 'B' = pamphlet/contribution
renewals (one row per renewal record):
  id, rdat (renewal date), oreg, odat (original registration number and date), author, title,
  claimants, new_matter, notes, source_file, title_norm, author_norm
Caveat: 1953+ catalog volumes include more small/ephemeral registrations, which lowers raw renewal rates."""


# --- The rules: U.S. copyright term for published works, as code ---------------------------------


def us_status(pub_year: int, published_in_us: bool = True, had_notice: bool | None = True,
              renewed: bool | None = None, renewal_year: int | None = None,
              author_death_year: int | None = None, foreign_status_known: str | None = None,
              today: dt.date | None = None) -> dict:
    """Deterministic U.S. status for a *published* book, after Copyright Office Circulars 15A and 22.

    renewed: True (documented renewal) / False (absence reported; NOT independently proven) / None.
    foreign_status_known: for non-U.S. works, 'pd_in_source_1996' if the work was already public domain
      in its source country on 1 Jan 1996 (then URAA did not restore it), else None.
    """
    today = today or dt.date.today()
    pd_cutoff = today.year - 96  # works published in or before this year are public domain in the U.S.
    steps, verdict, confidence = [], None, "high"
    steps.append(f"As of {today.isoformat()}, works published in {pd_cutoff} or earlier are in the U.S. "
                 f"public domain (95-year maximum term ended).")
    expires = pub_year + 96

    if pub_year <= pd_cutoff:
        verdict = "public_domain"
        steps.append(f"If this is the original published work from {pub_year}, the ordinary 95-year "
                     "U.S. maximum term has expired. Later editions, translations, and new matter "
                     "must be analyzed separately.")
    elif pub_year >= 1989:
        verdict = "in_copyright"
        steps.append("Published 1989 or later: no formalities; protected (life+70 or 95 years).")
    elif not published_in_us:
        steps.append("First published outside the U.S.: the 1996 URAA restored U.S. copyright to foreign works "
                     "that were still protected in their source country on 1 Jan 1996, even if never renewed "
                     "or published without notice.")
        if foreign_status_known == "pd_in_source_1996":
            verdict = "public_domain"
            confidence = "medium"
            steps.append("Already public domain in the source country on 1 Jan 1996, so not restored; "
                         "U.S. renewal records are then decisive only for its original U.S. term, which has ended.")
        else:
            verdict = "likely_in_copyright"
            confidence = "low"
            steps.append(f"Likely restored: protected until the end of {expires - 1} unless it was public domain "
                         "in its source country on 1 Jan 1996 (needs source-country law, which this data cannot settle).")
            if author_death_year:
                steps.append(f"Author died {author_death_year}; under a life+70 rule the source-country term "
                             f"{'had' if author_death_year + 70 < 1996 else 'had not'} ended by 1996 "
                             "(check the country's actual 1996 term).")
    elif pub_year <= 1977 and had_notice is False:
        verdict = "undetermined"
        confidence = "low"
        steps.append("The reported absence of copyright notice needs verification against the original "
                     "edition and applicable exceptions before a public-domain conclusion.")
    elif pub_year <= 1963:
        if renewed is True:
            verdict = "in_copyright"
            steps.append(f"U.S. work published {pub_year} with notice and renewed: protected for 95 years, "
                         f"until the end of {expires - 1}; public domain on 1 Jan {expires}.")
            if renewal_year and not (pub_year + 27 <= renewal_year <= pub_year + 28):
                confidence = "medium"
                steps.append(f"Renewal dated {renewal_year}, outside the 28th-year window "
                             f"({pub_year + 27}-{pub_year + 28}); check it is the renewal for this edition.")
        elif renewed is False:
            verdict = "undetermined"
            confidence = "low"
            steps.append("A search did not identify a renewal; this is not proof of non-renewal. "
                         "An independent, sufficiently complete investigation of original records "
                         "and applicable legal formalities is required before declaring public domain.")
        else:
            verdict = "undetermined"
            confidence = "low"
            steps.append("1931-1963 U.S. work: status depends on renewal, which has not been researched yet.")
    elif pub_year <= 1977:
        verdict = "in_copyright"
        steps.append(f"Published 1964-1977 with notice: renewal was automatic (1992 Act); protected until the end "
                     f"of {expires - 1}.")
    else:  # 1978 - Feb 1989
        verdict = "in_copyright" if had_notice is not False else "undetermined"
        steps.append("Published 1978-1989: protected if published with notice or registered within 5 years.")

    steps.append("Always caveats: a later edition's new text, illustrations, translations or forewords can be "
                 "separately protected; unpublished works follow different rules.")
    return {
        "eid": f"RULE:{pub_year}-{'us' if published_in_us else 'foreign'}-{renewed}",
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": steps,
        "public_domain_from": f"{expires}-01-01" if verdict in ("in_copyright", "likely_in_copyright") and pub_year < 1978 else None,
        "source": "U.S. Copyright Office Circular 15A (Duration) and Circular 22 (How to Investigate the "
                  "Copyright Status of a Work), https://www.copyright.gov/circs/circ22.pdf",
    }


# --- Live APIs -----------------------------------------------------------------------------------


def _get_json(url: str, params: dict | None = None) -> dict:
    r = HTTP.get(url, params=params)
    r.raise_for_status()
    return r.json()


def openlibrary_search(title: str, author: str | None = None, limit: int = 5) -> dict:
    fields = "key,title,author_name,first_publish_year,publisher,publish_place,oclc,lccn,edition_count,language,ebook_access"
    params = {"title": title, "limit": limit, "fields": fields}
    if author:
        params["author"] = author
    data = _get_json("https://openlibrary.org/search.json", params)
    out = []
    for d in data.get("docs", [])[:limit]:
        out.append({
            "eid": f"OL:{d.get('key', '').split('/')[-1]}",
            "url": f"https://openlibrary.org{d.get('key', '')}",
            "title": d.get("title"),
            "authors": d.get("author_name", [])[:3],
            "first_publish_year": d.get("first_publish_year"),
            "edition_count": d.get("edition_count"),
            "publishers": (d.get("publisher") or [])[:6],
            "publish_places": (d.get("publish_place") or [])[:6],
            "languages": (d.get("language") or [])[:5],
            "oclc": (d.get("oclc") or [])[:5],
            "lccn": (d.get("lccn") or [])[:5],
            "ebook_access": d.get("ebook_access"),
        })
    return {"source": "Open Library search API", "numFound": data.get("numFound"), "results": out}


def openlibrary_author(name: str, limit: int = 5) -> dict:
    """Search Open Library author authority records, keeping distinct candidates separate.

    A name match alone does not prove identity; aliases and dates are evidence to
    investigate, not an automatic merge. Open Library does not verify citizenship.
    """
    limit = max(1, min(int(limit), 10))
    data = _get_json("https://openlibrary.org/search/authors.json", {"q": name, "limit": limit})
    candidates = []
    query = norm(name)
    for d in data.get("docs", [])[:limit]:
        key = str(d.get("key") or "").split("/")[-1]
        if not re.fullmatch(r"OL[0-9]+A", key):
            continue
        aliases = d.get("alternate_names") or []
        birth = d.get("birth_date")
        death = d.get("death_date")
        # Relevance is a ranking hint only. Always expose alternate candidates.
        exact_name = norm(d.get("name")) == query
        exact_alias = any(norm(a) == query for a in aliases)
        candidates.append({
            "eid": f"OL:AUTHOR:{key}",
            "url": f"https://openlibrary.org/authors/{key}",
            "author_id": key,
            "source": "Open Library Authors API",
            "name": d.get("name"),
            "born": birth,
            "died": death,
            "alternate_names": aliases[:15],
            "match_score": (10 if exact_name else 0) + (4 if exact_alias else 0)
                           + (1 if birth else 0) + (1 if death else 0),
        })
    candidates.sort(key=lambda c: -c["match_score"])
    return {
        "source": "Open Library Authors API",
        "query": name,
        "results": candidates,
        "note": "Multiple author authority records can share a name. Do not merge candidates or treat dates "
                "from one candidate as proven for another. Verify identity using aliases, titles or other records. "
                "This API does not establish nationality, citizenship, or first-publication country.",
    }


HT_RIGHTS = {
    "pd": "public domain", "pdus": "public domain in the U.S.", "ic": "in copyright", "icus": "in copyright in the U.S.",
    "und": "undetermined (treated as in copyright)", "ic-world": "in copyright, world-viewable by permission",
    "op": "out of print (Section 108 access)", "nobody": "blocked", "cc-by-4.0": "Creative Commons",
}


def hathitrust_lookup(oclc: str | None = None, lccn: str | None = None) -> dict:
    if not (oclc or lccn):
        return {"error": "Give an OCLC or LCCN number (get one from openlibrary_search)."}
    kind, value = ("oclc", oclc) if oclc else ("lccn", lccn)
    data = _get_json(f"https://catalog.hathitrust.org/api/volumes/brief/{kind}/{value}.json")
    if "records" not in data and data:  # multi-id form wraps the answer in {query: {...}}
        data = next(iter(data.values()))
    records = data.get("records", {}) or {}
    items = []
    for it in (data.get("items") or [])[:10]:
        items.append({
            "eid": f"HT:{it.get('htid')}",
            "htid": it.get("htid"),
            "url": it.get("itemURL"),
            "rights_code": it.get("rightsCode"),
            "rights_meaning": HT_RIGHTS.get(it.get("rightsCode"), it.get("rightsCode")),
            "us_access": it.get("usRightsString"),
            "contributor": it.get("orig"),
        })
    recs = [{"record_url": r.get("recordURL"), "titles": r.get("titles"), "publish_dates": r.get("publishDates")}
            for r in records.values()][:3]
    return {
        "source": "HathiTrust Bibliographic API",
        "query": {kind: value},
        "records": recs,
        "items": items,
        "note": "rights_code pd/pdus with Full view means HathiTrust (often after manual CRMS review) treats the "
                "volume as public domain in the U.S.; ic/und means in copyright or not yet reviewed, not proof of renewal.",
    }


def wikidata_author(name: str) -> dict:
    hits = _get_json("https://www.wikidata.org/w/api.php", {
        "action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 5, "format": "json"})
    ids = [h["id"] for h in hits.get("search", [])]
    if not ids:
        return {"source": "Wikidata", "results": [], "note": f"No Wikidata item for {name!r}."}
    ents = _get_json("https://www.wikidata.org/w/api.php", {
        "action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims",
        "languages": "en", "format": "json"}).get("entities", {})

    def claim_ids(e, p):
        return [c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in e.get("claims", {}).get(p, [])]

    def year(e, p):
        for c in e.get("claims", {}).get(p, []):
            t = c["mainsnak"].get("datavalue", {}).get("value", {}).get("time")
            if t:
                return int(t[1:5]) if t[0] == "+" else -int(t[1:5])
        return None

    people = [e for e in (ents.get(i, {}) for i in ids) if "Q5" in claim_ids(e, "P31")][:2]  # humans only
    country_ids = {c for e in people for c in claim_ids(e, "P27") if c}
    labels = {}
    if country_ids:
        labels = {k: v.get("labels", {}).get("en", {}).get("value", k) for k, v in _get_json(
            "https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(sorted(country_ids)),
                                                   "props": "labels", "languages": "en", "format": "json"})
            .get("entities", {}).items()}
    out = [{
        "eid": f"WD:{e['id']}",
        "url": f"https://www.wikidata.org/wiki/{e['id']}",
        "name": e.get("labels", {}).get("en", {}).get("value"),
        "description": e.get("descriptions", {}).get("en", {}).get("value"),
        "born": year(e, "P569"),
        "died": year(e, "P570"),
        "citizenship": [labels.get(c, c) for c in claim_ids(e, "P27") if c],
    } for e in people]
    return {"source": "Wikidata", "results": out}


_pg_rows: list[dict] | None = None
_pg_lock = threading.Lock()
PG_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz"


def _gutenberg() -> list[dict]:
    global _pg_rows
    with _pg_lock:
        if _pg_rows is None:
            local = DATA / "pg_catalog.csv.gz"
            raw = local.read_bytes() if local.exists() else HTTP.get(PG_URL).content
            text = gzip.decompress(raw).decode("utf-8") if raw[:2] == b"\x1f\x8b" else raw.decode("utf-8")
            _pg_rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("Type") == "Text"]
    return _pg_rows


def gutenberg_search(title: str, author: str | None = None, limit: int = 5) -> dict:
    surname = _surname(author)
    hits = []
    for r in _gutenberg():
        if surname and surname not in norm(r.get("Authors")):
            continue
        s = fuzz.token_set_ratio(norm(title), norm(r.get("Title")))
        if s >= 70:
            hits.append((s, r))
    hits.sort(key=lambda x: -x[0])
    return {
        "source": "Project Gutenberg catalog (pg_catalog.csv)",
        "results": [{
            "eid": f"PG:{r['Text#']}",
            "url": f"https://www.gutenberg.org/ebooks/{r['Text#']}",
            "title": r.get("Title"), "authors": r.get("Authors"), "language": r.get("Language"),
            "match_score": s,
        } for s, r in hits[:limit]],
        "note": "Project Gutenberg (US) only posts texts it has cleared as U.S. public domain; the 'Issued' date "
                "is when Gutenberg posted it, not the original publication date.",
    }


EXTERNAL_SOURCES = {
    "openlibrary_search": "Open Library",
    "openlibrary_author": "Open Library Authors",
    "hathitrust_lookup": "HathiTrust",
    "wikidata_author": "Wikidata",
    "gutenberg_search": "Project Gutenberg",
}


def safe(fn, **kwargs) -> dict:
    """Call a data tool with explicit external-source outcomes.

    Preserve the existing local-tool result schema. For live external sources,
    distinguish a successful lookup with zero results from an unavailable source.
    Never make a false public-domain inference from either outcome.
    """
    name = getattr(fn, "__name__", type(fn).__name__)
    source = EXTERNAL_SOURCES.get(name)
    try:
        result = fn(**kwargs)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        error_status = "source_unavailable" if code in (401, 403, 429) or code >= 500 else "error"
        return {
            "status": error_status,
            "source": source or name,
            "results": [],
            "error": {"type": "http_status", "http_status": code, "message": f"HTTP {code} from {source or name}"},
            "coverage_note": "The source did not return research results. Do not interpret this as no matching records.",
        }
    except (httpx.TimeoutException, httpx.TransportError) as e:
        return {
            "status": "source_unavailable", "source": source or name, "results": [],
            "error": {"type": type(e).__name__, "message": str(e)[:180]},
            "coverage_note": "Network failure; not evidence of an absent record.",
        }
    except Exception as e:
        return {
            "status": "error", "source": source or name, "results": [],
            "error": {"type": type(e).__name__, "message": str(e)[:180]},
            "coverage_note": "The lookup failed; do not treat the error as an empty catalog.",
        }
    if not isinstance(result, dict):
        return {"status": "error", "source": source or name,
                "error": {"type": "invalid_response", "message": "Tool result was not a dict."}}
    if not source:
        return result  # Keep local records tools backward-compatible.
    if result.get("error"):
        return {"status": "error", "source": source, "results": [], "error": result["error"],
                "coverage_note": "Failed request or invalid input; not evidence that a record is absent."}
    result = dict(result)
    result["status"] = "success" if result.get("results", result.get("items", result.get("records", []))) else "no_results"
    result.setdefault("coverage_note", "Search results reflect this source and query only; absence is not proof of nonexistence.")
    result.setdefault("error", None)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(search_registrations("Strangers on a train", "Patricia Highsmith"), indent=1, default=str)[:1500])
    print(json.dumps(search_renewals("Strangers on a train", "Highsmith"), indent=1, default=str)[:800])
    print(json.dumps(us_status(1950, renewed=True, renewal_year=1977), indent=1))
    print(json.dumps(query_records("SELECT reg_year, count(*) n, round(100.0*count(renewal_id)/count(*),1) pct "
                                   "FROM reg_status WHERE regnum LIKE 'A%' AND reg_year BETWEEN 1950 AND 1952 GROUP BY 1 ORDER BY 1"), indent=1))
