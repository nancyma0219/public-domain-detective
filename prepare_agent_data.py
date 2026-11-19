#!/usr/bin/env python3
"""Bridge the existing NYPL DuckDB to the Parquet schema expected by records.py.

This does NOT infer non-renewal or public-domain status. A matched renewal is a
provisional record-level link, not a legal conclusion. Raw database is read-only.

Usage: python prepare_agent_data.py --db data/nypl.duckdb --out data
"""
import argparse
from pathlib import Path
import duckdb


def quote_path(path: Path) -> str:
    """Quote a local filesystem path for DuckDB SQL (COPY target cannot be bound)."""
    return "'" + str(path).replace("'", "''") + "'"


def export(database: Path, output: Path) -> None:
    if not database.is_file():
        raise SystemExit(f"Missing database: {database}. Run load_nypl.py --all-years first.")
    output.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH {quote_path(database.resolve())} AS nypl (READ_ONLY)")
        for table in ("registrations", "renewals"):
            con.execute(f"SELECT 1 FROM nypl.{table} LIMIT 1")

        print("Preparing normalized registration and renewal records ...", flush=True)
        con.execute("""
          CREATE TEMP TABLE reg_base AS
          SELECT
            entry_id,
            source_file,
            source_url,
            upper(regexp_replace(coalesce(regnum,''),'[^A-Za-z0-9]','','g')) AS regnum,
            CASE WHEN try_cast(reg_date AS DATE) IS NOT NULL
                 THEN cast(try_cast(reg_date AS DATE) AS VARCHAR) ELSE NULL END AS regdate,
            try_cast(substr(reg_date,1,4) AS INT) AS reg_year,
            try_cast(catalog_year AS INT) AS catalog_year,
            author AS authors, title, publisher,
            NULL::VARCHAR AS pubdate,
            trim(regexp_replace(lower(strip_accents(coalesce(title,''))), '[^a-z0-9]+', ' ', 'g')) AS title_norm,
            trim(regexp_replace(lower(strip_accents(coalesce(author,''))), '[^a-z0-9]+', ' ', 'g')) AS authors_norm
          FROM nypl.registrations
        """)
        con.execute("""
          CREATE TEMP TABLE ren_base AS
          SELECT
            entry_id,
            upper(regexp_replace(coalesce(renewal_regnum,''),'[^A-Za-z0-9]','','g')) AS id,
            CASE WHEN try_cast(renewal_date AS DATE) IS NOT NULL
                 THEN cast(try_cast(renewal_date AS DATE) AS VARCHAR) ELSE NULL END AS rdat,
            upper(regexp_replace(coalesce(original_regnum,''),'[^A-Za-z0-9]','','g')) AS oreg,
            CASE WHEN try_cast(original_reg_date AS DATE) IS NOT NULL
                 THEN cast(try_cast(original_reg_date AS DATE) AS VARCHAR) ELSE NULL END AS odat,
            author, title, claimants, new_matter, notes, source_file,
            trim(regexp_replace(lower(strip_accents(coalesce(title,''))), '[^a-z0-9]+', ' ', 'g')) AS title_norm,
            trim(regexp_replace(lower(strip_accents(coalesce(author,''))), '[^a-z0-9]+', ' ', 'g')) AS author_norm
          FROM nypl.renewals
        """)

        # Multiple rows for one composite key are not automatically duplicates.
        # We only attach a renewal where both sides have no recorded identity collision.
        con.execute("""
          CREATE TEMP TABLE reg_keys AS
          SELECT regnum, regdate,
                 count(DISTINCT title_norm) AS title_variants,
                 count(DISTINCT authors_norm) AS author_variants,
                 count(*) AS source_rows
          FROM reg_base
          WHERE regnum <> '' AND regdate IS NOT NULL
          GROUP BY 1, 2
        """)
        con.execute("""
          CREATE TEMP TABLE ren_keys AS
          SELECT oreg, odat, count(DISTINCT id) AS renewal_variants,
                 count(*) AS source_rows,
                 min(id) AS candidate_renewal_id,
                 min(rdat) AS candidate_renewal_date,
                 min(claimants) AS candidate_claimants
          FROM ren_base
          WHERE oreg <> '' AND odat IS NOT NULL AND id <> ''
          GROUP BY 1, 2
        """)
        con.execute("""
          CREATE TEMP TABLE reg_status AS
          SELECT r.entry_id, r.source_file, r.source_url, r.regnum,
                 r.regdate, r.reg_year, r.catalog_year, r.authors, r.title,
                 r.publisher, r.pubdate, r.title_norm, r.authors_norm,
                 CASE WHEN rk.title_variants = 1 AND rk.author_variants = 1
                           AND nk.renewal_variants = 1
                      THEN nk.candidate_renewal_id ELSE NULL END AS renewal_id,
                 CASE WHEN rk.title_variants = 1 AND rk.author_variants = 1
                           AND nk.renewal_variants = 1
                      THEN nk.candidate_renewal_date ELSE NULL END AS renewal_date,
                 CASE WHEN rk.title_variants = 1 AND rk.author_variants = 1
                           AND nk.renewal_variants = 1
                      THEN nk.candidate_claimants ELSE NULL END AS renewal_claimants,
                 CASE WHEN r.regnum = '' OR r.regdate IS NULL THEN 'invalid_registration_key'
                      WHEN rk.title_variants > 1 OR rk.author_variants > 1 THEN 'registration_key_collision'
                      WHEN nk.renewal_variants > 1 THEN 'multiple_renewal_candidates'
                      WHEN nk.renewal_variants = 1 THEN 'exact_key_candidate'
                      ELSE 'no_exact_key_match' END AS match_status
          FROM reg_base r
          LEFT JOIN reg_keys rk ON r.regnum = rk.regnum AND r.regdate = rk.regdate
          LEFT JOIN ren_keys nk ON r.regnum = nk.oreg AND r.regdate = nk.odat
        """)

        # Shard by catalog year to stay under GitHub's per-file limit where possible.
        spans = [(1923,1934), (1935,1946), (1947,1958), (1959,1969), (1970,1977)]
        files = []
        for start, end in spans:
            path = output / f"reg_status_{start}_{end}.parquet"
            con.execute(f"COPY (SELECT * FROM reg_status WHERE catalog_year BETWEEN {start} AND {end}) TO {quote_path(path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
            files.append(path)
            print(f"{path.name}: {path.stat().st_size/1024/1024:.1f} MiB", flush=True)
        other_count = con.execute("SELECT count(*) FROM reg_status WHERE catalog_year IS NULL OR catalog_year < 1923 OR catalog_year > 1977").fetchone()[0]
        if other_count:
            path = output / "reg_status_other.parquet"
            con.execute(f"COPY (SELECT * FROM reg_status WHERE catalog_year IS NULL OR catalog_year < 1923 OR catalog_year > 1977) TO {quote_path(path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
            files.append(path)
            print(f"{path.name}: {path.stat().st_size/1024/1024:.1f} MiB")
        path = output / "renewals.parquet"
        con.execute(f"COPY ren_base TO {quote_path(path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        files.append(path)
        print(f"{path.name}: {path.stat().st_size/1024/1024:.1f} MiB")

        print("\n=== EXPORT CHECK ===")
        print("Registration rows:", con.execute("SELECT count(*) FROM reg_status").fetchone()[0])
        print("Renewal rows:", con.execute("SELECT count(*) FROM ren_base").fetchone()[0])
        for label, count in con.execute("SELECT match_status, count(*) FROM reg_status GROUP BY 1 ORDER BY 1").fetchall():
            print(f"  {label}: {count:,}")
        exported = con.execute(f"SELECT count(*) FROM read_parquet({quote_path(output / 'reg_status_*.parquet')})").fetchone()[0]
        original = con.execute("SELECT count(*) FROM nypl.registrations").fetchone()[0]
        if exported != original:
            raise RuntimeError(f"Row count mismatch: exported {exported}, original {original}")
        if any(p.stat().st_size >= 100_000_000 for p in files):
            print("WARNING: One or more Parquet files exceed GitHub's 100 MB limit. Use GCS or smaller shards.")
        print("All registration rows accounted for. These are RECORD links, NOT final legal verdicts.")
    finally:
        con.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, default=Path('data/nypl.duckdb'))
    p.add_argument('--out', type=Path, default=Path('data'))
    a = p.parse_args()
    export(a.db, a.out)
