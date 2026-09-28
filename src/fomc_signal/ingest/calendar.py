"""Parse the FOMC meeting calendars into one row per meeting/action.

Two page layouts exist on federalreserve.gov:

* ``/monetarypolicy/fomccalendars.htm`` (recent ~5 years): one ``div.fomc-meeting``
  per meeting inside a panel headed "YYYY FOMC Meetings".
* ``/monetarypolicy/fomchistoricalYYYY.htm`` (archive): one ``<h5>`` heading per
  meeting/call ("January 30-31 Meeting - 1996", "March 2 (unscheduled) Meeting - 2020",
  "March 25 Conference Call - 2003", "March 19 (notation vote) - 2020"), followed by
  the links for that event.

Statement and minutes URLs are recorded as found; their formats differ by era.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}
# full or abbreviated month names ("January", "Jan", "Sept")
_MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_ABBR = {m[:3]: i for m, i in MONTHS.items()}


def month_number(name: str) -> int:
    """Month number from a full or abbreviated English month name ("Apr", "April")."""
    return _ABBR[name.strip().rstrip(".").lower()[:3]]

STATEMENT_HREF = re.compile(
    r"(/newsevents/press(?:releases)?/monetary/?\d{8}[a-z]\d?\.htm"
    r"|/boarddocs/press/(?:monetary|general)/\d{4}/\d{8}/(?:default\.htm)?"
    r"|/fomc/\d{8}default\.htm)$",
    re.IGNORECASE,
)
MINUTES_HREF = re.compile(
    r"(/monetarypolicy/fomc(?:minutes)?\d{8}\.htm|/fomc/minutes/(?:\d{4}/)?\d{8}(?:min)?\.htm)$",
    re.IGNORECASE,
)
RELEASED_RE = re.compile(r"Released\s+([A-Z][a-z]+\.?\s+\d{1,2},\s*\d{4})")


@dataclass
class MeetingRow:
    """One FOMC meeting or unscheduled action as listed on a calendar page."""

    year: int
    label: str               # heading/date text as shown on the page
    meeting_start: date
    meeting_end: date        # last day of the meeting (decision day)
    event_type: str          # scheduled | unscheduled | conference_call | notation_vote | cancelled
    scheduled: bool
    statement_url: str | None
    minutes_url: str | None
    minutes_release_date: date | None
    source_page: str

    def as_dict(self) -> dict:
        """Return the row as a plain dict."""
        return asdict(self)


def classify_event(label: str) -> str:
    """Classify a calendar label into an event type (scheduled or an unscheduled kind)."""
    low = label.lower()
    if "cancel" in low:
        return "cancelled"
    if "notation vote" in low:
        return "notation_vote"
    if "conference call" in low:
        return "conference_call"
    if "unscheduled" in low:
        return "unscheduled"
    return "scheduled"


def parse_date_span(text: str, year: int, default_month: str | None = None) -> tuple[date, date]:
    """Parse "January 30-31", "April 30-May 1", "30-1" (with default_month "April/May")
    or "22" into (start, end) dates. Cross-year spans are not handled (none exist)."""
    text = re.sub(r"\(.*?\)|\*", "", text).strip()
    text = text.replace("–", "-").replace("—", "-")
    pair = re.match(rf"^((?:{_MONTH_RE})/(?:{_MONTH_RE}))\s+", text)
    if pair:  # archive form "April/May 30-1"
        default_month, text = pair.group(1), text[pair.end():]
    m = re.match(
        rf"^(?:({_MONTH_RE})\s+)?(\d{{1,2}})(?:\s*-\s*(?:({_MONTH_RE})\s+)?(\d{{1,2}}))?",
        text,
    )
    if not m:
        raise ValueError(f"unparseable meeting date: {text!r}")
    m1, d1, m2, d2 = m.groups()
    months = (default_month or "").split("/")
    start_month = month_number(m1 or months[0])
    if d2 is None:
        d = date(year, start_month, int(d1))
        return d, d
    if m2:
        end_month = month_number(m2)
    elif len(months) == 2 and not m1:
        end_month = month_number(months[1])
    else:
        end_month = start_month
    return date(year, start_month, int(d1)), date(year, end_month, int(d2))


def parse_release_date(text: str) -> date | None:
    """Extract the "(Released Month D, YYYY)" date from a snippet, if any."""
    m = RELEASED_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(".", "")
    mon, rest = raw.split(" ", 1)
    day, yr = rest.replace(" ", "").split(",")
    return date(int(yr), month_number(mon), int(day))


def _links(block: list[Tag]) -> list[tuple[str, str]]:
    out = []
    for el in block:
        anchors = [el] if el.name == "a" else el.find_all("a")
        for a in anchors:
            href = (a.get("href") or "").strip()
            href = re.sub(r"^https?://www\.federalreserve\.gov", "", href)
            out.append((href, a.get_text(" ", strip=True)))
    return out


def _pick_urls(block: list[Tag]) -> tuple[str | None, str | None, date | None]:
    links = _links(block)
    statement = next((h for h, _ in links if STATEMENT_HREF.search(h)), None)
    # anchors with '#' point into another meeting's minutes ("see end of minutes of ...")
    minutes = next((h for h, _ in links if "#" not in h and MINUTES_HREF.search(h)), None)
    text = " ".join(el.get_text(" ", strip=True) for el in block)
    # "(Released ...)" belongs to the minutes; search after the "Minutes" label if present
    idx = text.find("Minutes")
    released = parse_release_date(text[max(idx, 0):])
    return statement, minutes, released


def parse_historical_year(html: str, year: int, source_page: str) -> list[MeetingRow]:
    """Parse one ``fomchistoricalYYYY.htm`` page."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[MeetingRow] = []
    for h5 in soup.find_all("h5"):
        label = h5.get_text(" ", strip=True)
        if not re.search(rf"({_MONTH_RE})", label):
            continue
        # the links live in the panel enclosing the heading (the heading sits either
        # directly in the panel or inside a div.panel-heading, depending on the year)
        panel = h5.find_parent("div", class_="panel")
        block = [panel] if panel is not None else []
        head = re.sub(r"\s*-\s*\d{4}\s*$", "", label)
        head_dates = re.sub(r"\s+(Meeting|Conference Call)\b.*$", "", head)
        start, end = parse_date_span(head_dates, year)
        statement, minutes, released = _pick_urls(block)
        etype = classify_event(label)
        rows.append(MeetingRow(year, label, start, end, etype, etype == "scheduled",
                               statement, minutes, released, source_page))
    return rows


def parse_recent_calendar(html: str, source_page: str) -> list[MeetingRow]:
    """Parse ``fomccalendars.htm`` (recent years, including future scheduled dates)."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[MeetingRow] = []
    for panel_head in soup.find_all(string=re.compile(r"^\s*\d{4} FOMC Meetings\s*$")):
        year = int(panel_head.strip()[:4])
        panel = panel_head.find_parent("div", class_="panel")
        if panel is None:
            continue
        for mtg in panel.find_all("div", class_="fomc-meeting"):
            month_el = mtg.find(class_="fomc-meeting__month")
            date_el = mtg.find(class_="fomc-meeting__date")
            if month_el is None or date_el is None:
                continue
            month_txt = month_el.get_text(" ", strip=True)
            date_txt = date_el.get_text(" ", strip=True)
            start, end = parse_date_span(date_txt, year, default_month=month_txt)
            statement, minutes, released = _pick_urls([mtg])
            label = f"{month_txt} {date_txt}"
            etype = classify_event(label)
            rows.append(MeetingRow(year, label, start, end, etype, etype == "scheduled",
                                   statement, minutes, released, source_page))
    return rows


def statement_date_from_url(url: str | None) -> date | None:
    """Release date embedded in a statement URL (the 8-digit YYYYMMDD stamp)."""
    if not url:
        return None
    m = re.search(r"(\d{8})", url)
    return datetime.strptime(m.group(1), "%Y%m%d").date() if m else None
