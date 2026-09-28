"""Turn cached statement/minutes pages into paragraphs, and extract release times.

Layouts handled:

* 1994-2005 archive pages (``/fomc/...default.htm``, ``/boarddocs/press/...``,
  ``/fomc/minutes/...``): bare HTML, text hard-wrapped inside ``<p>``, body delimited
  by "For immediate release" and a footer.
* 2006+ pages: the document lives in ``div#article``.

Release time sources, in order of preference (recorded in ``time_source``):

1. ``statement_page``: "For release at 2:00 p.m. EST" on the statement page (2013+).
2. ``minutes``: the meeting's minutes, which record e.g. "the statement below to be
   released at 2:15 p.m." (most years since the late 1990s).
3. otherwise the time is left null (``unverified``); no single time is assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time

from bs4 import BeautifulSoup, NavigableString, Comment

BLOCK_TAGS = [
    "p", "div", "li", "ul", "ol", "table", "tr", "td", "th", "h1", "h2", "h3",
    "h4", "h5", "h6", "blockquote", "pre", "br", "hr", "dd", "dt",
]
_WS = re.compile(r"\s+")


def html_to_paragraphs(html: str, prefer_article: bool = True) -> list[str]:
    """Extract whitespace-normalised paragraphs from an HTML page.

    Raw newlines inside text are treated as spaces (old pages hard-wrap lines);
    block-level tags and ``<br>`` delimit paragraphs. If the page has a
    ``div#article`` (2006+ layout) only its content is used.
    """
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    root = (soup.find(id="article") if prefer_article else None) or soup.body or soup
    for s in list(root.find_all(string=True)):
        if isinstance(s, NavigableString):
            s.replace_with(_WS.sub(" ", str(s)))
    for tag in root.find_all(BLOCK_TAGS):
        tag.insert_before("\n\n")
        tag.insert_after("\n\n")
    text = root.get_text("")
    paras = [_WS.sub(" ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p]


# --- release times --------------------------------------------------------------

_TIME = r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?"
STATEMENT_PAGE_TIME = re.compile(rf"For release at\s+{_TIME}", re.IGNORECASE)
# "... statement below to be released at 2:15 p.m.", "statement below for release at 2:00 p.m."
MINUTES_STATEMENT_TIME = re.compile(
    rf"statement[^.]{{0,80}}?(?:to be\s+)?(?:released|for release)\s+at\s+{_TIME}",
    re.IGNORECASE,
)


def _to_time(h: str, m: str | None, ampm: str) -> time:
    hour = int(h) % 12 + (12 if ampm.lower() == "p" else 0)
    return time(hour, int(m or 0))


def release_time_from_statement_page(paragraphs: list[str]) -> time | None:
    """Release time printed on a statement page ("For release at 2:00 p.m. EST")."""
    for p in paragraphs[:12]:
        m = STATEMENT_PAGE_TIME.search(p)
        if m:
            return _to_time(*m.groups())
    return None


def statement_times_in_minutes(paragraphs: list[str]) -> list[time]:
    """All statement release times mentioned in a minutes document, in order.

    Minutes can also mention statements of intermeeting calls (e.g. "released at
    8:30 a.m. on Tuesday, January 22"); callers must check for ambiguity.
    """
    text = " ".join(paragraphs)
    out = []
    for m in MINUTES_STATEMENT_TIME.finditer(text):
        # skip mentions that name another day ("... at 8:30 a.m. on Tuesday, January 22")
        tail = text[m.end(): m.end() + 40]
        if re.match(r"\s*(?:\(EDT\)|\(EST\)|EDT|EST)?\s*,?\s*on\s+\w+day", tail):
            continue
        out.append(_to_time(*m.groups()))
    return out


@dataclass
class ReleaseTime:
    """A statement release time and where it came from."""

    time: time | None
    source: str  # statement_page | minutes | unverified
    note: str = ""


MINUTES_PR_TITLE = re.compile(r"Minutes of (the )?Federal Open Market Committee", re.IGNORECASE)


def minutes_press_release_urls(release_date) -> list[str]:
    """Candidate press-release URLs announcing minutes released on ``release_date``.

    The Board numbers same-day releases a, b, c, ...; the page title identifies the
    minutes ("Minutes of [the] Federal Open Market Committee, ...").
    """
    stamp = release_date.strftime("%Y%m%d")
    return [f"/newsevents/pressreleases/monetary{stamp}{s}.htm" for s in "abcde"]


def minutes_release_time(fetch, release_date) -> tuple[ReleaseTime, str | None]:
    """Find the minutes press release for ``release_date`` and read its release time.

    ``fetch`` is a callable url -> html | None. Returns the time (or unverified) and
    the press-release URL that was matched, if any.
    """
    for url in minutes_press_release_urls(release_date):
        html = fetch(url)
        if html is None:
            break  # suffixes are consecutive; a gap means no more releases that day
        paras = html_to_paragraphs(html)
        if any(MINUTES_PR_TITLE.search(p) for p in paras[:4]):
            t = release_time_from_statement_page(paras)
            if t == time(0, 0):  # e.g. 2008-01-02 prints "12:00 a.m."; not trusted
                return ReleaseTime(None, "unverified", "press release says 12:00 a.m. (implausible)"), url
            if t is not None:
                return ReleaseTime(t, "minutes_press_release"), url
            return ReleaseTime(None, "unverified", "press release has no time"), url
    return ReleaseTime(None, "unverified", "no minutes press release found"), None


def resolve_statement_time(
    statement_paras: list[str], minutes_paras: list[str] | None
) -> ReleaseTime:
    """Pick the statement release time: statement page first, then its minutes."""
    t = release_time_from_statement_page(statement_paras)
    if t is not None:
        return ReleaseTime(t, "statement_page")
    if minutes_paras:
        times = statement_times_in_minutes(minutes_paras)
        distinct = sorted(set(times))
        if len(distinct) == 1:
            return ReleaseTime(distinct[0], "minutes")
        if len(distinct) > 1:
            return ReleaseTime(None, "unverified",
                               "ambiguous times in minutes: " + ",".join(map(str, distinct)))
    return ReleaseTime(None, "unverified", "no time found")
