"""Phase 1 entry point: scrape (cached), parse and clean FOMC statements and minutes.

Writes data/processed/{meetings,documents,stripped}.parquet and prints the
checkpoint summary. Re-runnable: pages already in data/cache/html are never
downloaded again.
"""

from __future__ import annotations

import argparse
from datetime import date

import polars as pl

from fomc_signal.ingest.http import CachedFetcher
from fomc_signal.ingest.pipeline import build_documents, load_meetings
from fomc_signal.paths import HTML_CACHE, PROCESSED


def summarise(meetings: pl.DataFrame, docs: pl.DataFrame, stripped: pl.DataFrame) -> None:
    """Print the phase 1 checkpoint: counts by year/type, date range, gaps."""
    pl.Config.set_tbl_rows(100)
    pl.Config.set_tbl_width_chars(200)
    pl.Config.set_fmt_str_lengths(70)
    counts = (
        docs.with_columns(pl.col("meeting_end").dt.year().alias("year"),
                          pl.when(pl.col("scheduled")).then(pl.col("doc_type"))
                          .otherwise(pl.col("doc_type") + "_unsched").alias("kind"))
        .group_by("year", "kind").len()
        .pivot(on="kind", index="year", values="len").sort("year").fill_null(0)
    )
    print("\nDocuments by meeting year and type")
    print(counts)
    for dt in ("statement", "minutes"):
        d = docs.filter(pl.col("doc_type") == dt)
        print(f"{dt}: {d.height} docs, release dates {d['release_date'].min()} .. {d['release_date'].max()}")
    print("\nRelease-time source by doc type")
    print(docs.group_by("doc_type", "time_source", "release_time_et").len()
          .sort("doc_type", "time_source", "release_time_et"))
    sched = meetings.filter(pl.col("scheduled"))
    print("\nScheduled meetings without a statement page")
    print(sched.filter(pl.col("statement_url").is_null()).select("label"))
    print("\nScheduled meetings without separate minutes")
    print(sched.filter(pl.col("minutes_url").is_null()).select("label"))
    print("\nStripped text by rule")
    print(stripped.group_by("rule").agg(pl.len(), pl.col("text").str.len_chars().sum().alias("chars")).sort("rule"))


def main() -> None:
    """Run phase 1."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(),
                    help="ignore meetings after this date (default: today)")
    args = ap.parse_args()

    fetcher = CachedFetcher(HTML_CACHE)
    meetings = load_meetings(fetcher, args.today)
    docs, stripped = build_documents(meetings, fetcher)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    meetings.write_parquet(PROCESSED / "meetings.parquet")
    docs.write_parquet(PROCESSED / "documents.parquet")
    stripped.write_parquet(PROCESSED / "stripped.parquet")
    print(f"network requests: {fetcher.n_network}, cache hits: {fetcher.n_cached}")
    summarise(meetings, docs, stripped)


if __name__ == "__main__":
    main()
