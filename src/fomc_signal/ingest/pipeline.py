"""Phase 1 pipeline: calendars -> meetings table -> cleaned documents table."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from fomc_signal.ingest.calendar import (
    MeetingRow, parse_historical_year, parse_recent_calendar, statement_date_from_url,
    parse_date_span, _MONTH_RE,
)
from fomc_signal.ingest.clean import clean_minutes, clean_statement
from fomc_signal.ingest.documents import (
    html_to_paragraphs, minutes_release_time, resolve_statement_time,
)
from fomc_signal.ingest.http import CachedFetcher

ET = ZoneInfo("America/New_York")
FIRST_YEAR = 1994          # first year with FOMC statements
LAST_ARCHIVE_YEAR = 2020   # later years are on the current calendar page
RECENT_PAGE = "/monetarypolicy/fomccalendars.htm"
_PAGE_DATE = re.compile(rf"({_MONTH_RE})\s+(\d{{1,2}}),\s*(\d{{4}})")


def load_meetings(fetcher: CachedFetcher, today: date) -> pl.DataFrame:
    """All FOMC meetings and unscheduled actions since 1994 up to ``today``."""
    rows: list[MeetingRow] = []
    for year in range(FIRST_YEAR, LAST_ARCHIVE_YEAR + 1):
        page = f"/monetarypolicy/fomchistorical{year}.htm"
        rows += parse_historical_year(fetcher.get(page), year, page)
    rows += parse_recent_calendar(fetcher.get(RECENT_PAGE), RECENT_PAGE)
    df = pl.DataFrame([r.as_dict() for r in rows])
    return (
        df.filter(pl.col("meeting_end") <= today)
        .unique(subset=["meeting_end", "label"], keep="first")
        .sort("meeting_end")
    )


def page_date(paragraphs: list[str]) -> date | None:
    """First "Month D, YYYY" date near the top of a page (the printed release date)."""
    for p in paragraphs[:8]:
        m = _PAGE_DATE.search(p)
        if m:
            start, _ = parse_date_span(f"{m.group(1)} {m.group(2)}", int(m.group(3)))
            return start
    return None


def _et(d: date | None, t) -> datetime | None:
    return datetime.combine(d, t, tzinfo=ET) if (d is not None and t is not None) else None


def build_documents(meetings: pl.DataFrame, fetcher: CachedFetcher
                    ) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Fetch, parse and clean every statement and minutes document.

    Returns (documents, stripped_log). Documents carry release date/time with the
    source of the time; stripped_log has one row per removed paragraph/sentence.
    """
    docs, stripped = [], []
    for m in meetings.iter_rows(named=True):
        st_paras = mn_paras = None
        if m["statement_url"]:
            html = fetcher.get(m["statement_url"])
            st_paras = html_to_paragraphs(html) if html else None
        if m["minutes_url"]:
            html = fetcher.get(m["minutes_url"])
            mn_paras = html_to_paragraphs(html) if html else None

        base = {k: m[k] for k in ("meeting_start", "meeting_end", "event_type", "scheduled", "label")}
        if st_paras:
            url_date = statement_date_from_url(m["statement_url"])
            printed = page_date(st_paras)
            rt = resolve_statement_time(st_paras, mn_paras)
            res = clean_statement(st_paras)
            # the date printed on the page wins; a few archive URLs carry a wrong date stamp
            rel = printed or url_date
            doc_id = f"statement_{rel}_{m['event_type']}"
            docs.append({
                **base, "doc_id": doc_id, "doc_type": "statement",
                "release_date": rel,
                "release_date_check": "ok" if url_date in (None, rel) else f"url says {url_date}",
                "release_time_et": rt.time, "release_datetime": _et(rel, rt.time),
                "time_source": rt.source, "time_note": rt.note,
                "source_url": fetcher.absolute(m["statement_url"]),
                "raw_text": "\n\n".join(st_paras), "clean_text": res.text,
                "n_words": len(res.text.split()),
            })
            stripped += [{"doc_id": doc_id, "rule": r, "text": t} for r, t in res.stripped]
        if mn_paras:
            res = clean_minutes(mn_paras)
            rel = m["minutes_release_date"]
            doc_id = f"minutes_{m['meeting_end']}_{m['event_type']}"
            # minutes pages carry no release time; read it from the minutes press release
            rt, pr_url = minutes_release_time(fetcher.get, rel) if rel else (None, None)
            docs.append({
                **base, "doc_id": doc_id, "doc_type": "minutes",
                "release_date": rel, "release_date_check": "calendar" if rel else "missing",
                "release_time_et": rt.time if rt else None,
                "release_datetime": _et(rel, rt.time) if rt else None,
                "time_source": rt.source if rt else "unverified",
                "time_note": (rt.note if rt else "no release date") + (f" [{pr_url}]" if pr_url else ""),
                "source_url": fetcher.absolute(m["minutes_url"]),
                "raw_text": "\n\n".join(mn_paras), "clean_text": res.text,
                "n_words": len(res.text.split()),
            })
            stripped += [{"doc_id": doc_id, "rule": r, "text": t} for r, t in res.stripped]

    documents = pl.DataFrame(docs, infer_schema_length=None).with_columns(
        pl.col("release_datetime").cast(pl.Datetime("us", time_zone="America/New_York"))
    )
    return documents.sort("release_date", "doc_type"), pl.DataFrame(stripped)
