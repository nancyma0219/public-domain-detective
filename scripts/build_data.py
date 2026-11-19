"""Offline build step: NYPL Catalog of Copyright Entries -> Parquet files for the agent.

Inputs (clone these first):
  git clone --depth 1 https://github.com/NYPL/catalog_of_copyright_entries_project   (~1.7 GB, XML)
  git clone --depth 1 https://github.com/NYPL/cce-renewals                           (~140 MB, TSV)

Usage:
    uv run --group build scripts/build_data.py data/nypl_registrations data/nypl_renewals data/

Outputs (each < 100 MB, so they can be committed to GitHub):
  data/reg_status_*.parquet  one row per registration (1923-1969 book volumes),
                           with the matching renewal (if any) joined on regnum + regdate
  data/renewals.parquet    every renewal record (1950-1991 + a few later years)
Takes ~2 minutes on a laptop.
"""
import csv
import glob
import os
import sys

import duckdb
from lxml import etree

reg_dir, ren_dir, out_dir = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)
YEARS = range(1923, 1970)  # book volumes transcribed by NYPL


def norm_regnum(s):
    return (s or "").replace("-", "").replace(" ", "") or None


def iter_registrations():
    """Yield one row per registration number (an entry can carry several via <additionalEntry>)."""
    for year in YEARS:
        for f in sorted(glob.glob(os.path.join(reg_dir, "xml", str(year), "*.xml"))):
            for _, e in etree.iterparse(f, tag="copyrightEntry", load_dtd=False, no_network=True,
                                        recover=True, resolve_entities=False, huge_tree=True):
                authors = "; ".join(" ".join(a.itertext()).strip() for a in e.findall("author/authorName"))
                title_el = e.find("title")
                pub = e.find("publisher/pubName")
                pubdate = e.find("publisher/pubDate")
                regs = [(e.findtext("regNum"), e.find("regDate"))]
                regs += [(ae.findtext("regNum"), ae.find("regDate")) for ae in e.findall("additionalEntry")]
                for num, rd in regs:
                    yield (
                        e.get("id"), os.path.basename(f), norm_regnum(num),
                        rd.get("date") if rd is not None else None,
                        authors or None,
                        " ".join(title_el.itertext()).strip() if title_el is not None else None,
                        " ".join(pub.itertext()).strip() if pub is not None else None,
                        pubdate.get("date") if pubdate is not None else None,
                        " ".join(e.itertext()).strip(),
                    )
                e.clear()  # keep memory flat
                while e.getprevious() is not None:
                    del e.getparent()[0]


# 1) registrations -> temporary TSV (bulk load is far faster than row inserts)
cols = ["entry_id", "source_file", "regnum", "regdate", "authors", "title", "publisher", "pubdate", "full_text"]
tmp = os.path.join(out_dir, "_registrations.tsv")
with open(tmp, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(cols)
    for i, row in enumerate(iter_registrations(), 1):
        w.writerow(["" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in row])
        if i % 250000 == 0:
            print(f"parsed {i:,} registrations", flush=True)

con = duckdb.connect()
con.execute(f"""CREATE TABLE registrations AS SELECT * FROM read_csv('{tmp}', delim='\\t', header=true,
                quote='"', escape='"', all_varchar=true)""")
os.remove(tmp)

# 2) renewals: two schemas (CCE transcriptions vs. post-1978 Copyright Office database exports)
base = os.path.join(ren_dir, "data")


def renewals_select(pattern, author, title, rdat, notes):
    return f"""SELECT entry_id, volume, oreg, odat, id, {rdat} AS rdat, {author} AS author, {title} AS title,
                      claimants, new_matter, {notes} AS notes, full_text,
                      regexp_extract(filename, '([^/]+)\\.tsv$', 1) AS source_file
               FROM read_csv('{base}/{pattern}', delim='\\t', header=true, all_varchar=true, quote='',
                             filename=true, union_by_name=true, ignore_errors=true)"""


con.execute("CREATE TABLE renewals AS "
            + renewals_select("[0-9][0-9][0-9][0-9]-[0-9]*.tsv", "author", "title", "rdat", "notes")
            + " UNION ALL BY NAME "
            + renewals_select("*-from-db.tsv", "auth", "titl", "dreg", "note"))

# 3) match renewals to registrations on registration number AND date
#    (numbers restart in 1947, so the number alone is not unique - see cce-renewals README).
#    Also add normalized title/author columns that the agent's fuzzy search uses.
NORM = "trim(regexp_replace(lower(strip_accents(coalesce({c}, ''))), '[^a-z0-9]+', ' ', 'g'))"
con.execute(f"""CREATE TABLE reg_status AS
  SELECT r.entry_id, r.source_file, r.regnum, r.regdate,
         try_cast(substr(r.regdate, 1, 4) AS INT) AS reg_year,
         r.authors, r.title, r.publisher, r.pubdate,
         {NORM.format(c='r.title')} AS title_norm,
         {NORM.format(c='r.authors')} AS authors_norm,
         n.id AS renewal_id, n.rdat AS renewal_date, n.claimants AS renewal_claimants
  FROM registrations r
  LEFT JOIN (SELECT DISTINCT oreg, odat, id, rdat, claimants FROM renewals) n
    ON r.regnum = n.oreg AND r.regdate = n.odat""")
con.execute(f"""CREATE OR REPLACE TABLE renewals AS
  SELECT *, {NORM.format(c='title')} AS title_norm, {NORM.format(c='author')} AS author_norm FROM renewals""")

# Two files, so each stays well under GitHub's 100 MB limit; the app reads reg_status_*.parquet
con.execute(f"COPY (FROM reg_status WHERE reg_year < 1955 OR reg_year IS NULL) TO '{out_dir}/reg_status_1923_1954.parquet' (FORMAT parquet, COMPRESSION zstd)")
con.execute(f"COPY (FROM reg_status WHERE reg_year >= 1955) TO '{out_dir}/reg_status_1955_1969.parquet' (FORMAT parquet, COMPRESSION zstd)")
con.execute(f"COPY renewals TO '{out_dir}/renewals.parquet' (FORMAT parquet, COMPRESSION zstd)")
for t in ("registrations", "renewals", "reg_status"):
    print(t, f"{con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:,} rows")
