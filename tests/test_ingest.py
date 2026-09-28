"""Phase 1 tests: calendar parsing, HTML extraction, cleaning, sentence splitting, release times."""

from datetime import date, time

import pytest

from fomc_signal.ingest.calendar import (
    classify_event, parse_date_span, parse_historical_year, parse_recent_calendar,
    parse_release_date, statement_date_from_url,
)
from fomc_signal.ingest.clean import clean_minutes, clean_statement, split_sentences
from fomc_signal.ingest.documents import (
    html_to_paragraphs, release_time_from_statement_page, resolve_statement_time,
    statement_times_in_minutes,
)
from fomc_signal.ingest.http import cache_path, decode_body


# --- calendar -------------------------------------------------------------------

@pytest.mark.parametrize("text,default,expected", [
    ("January 30-31", None, (date(1996, 1, 30), date(1996, 1, 31))),
    ("June 30-July 1", None, (date(1996, 6, 30), date(1996, 7, 1))),
    ("April/May 30-1", None, (date(1996, 4, 30), date(1996, 5, 1))),
    ("Jan/Feb 31-1", None, (date(1996, 1, 31), date(1996, 2, 1))),
    ("30-1", "Apr/May", (date(1996, 4, 30), date(1996, 5, 1))),
    ("18-19*", "March", (date(1996, 3, 18), date(1996, 3, 19))),
    ("22 (notation vote)", "August", (date(1996, 8, 22), date(1996, 8, 22))),
    ("March  4 (unscheduled)", None, (date(1996, 3, 4), date(1996, 3, 4))),
])
def test_parse_date_span(text, default, expected):
    assert parse_date_span(text, 1996, default_month=default) == expected


@pytest.mark.parametrize("label,etype", [
    ("January 30-31 Meeting - 1996", "scheduled"),
    ("March 2 (unscheduled) Meeting - 2020", "unscheduled"),
    ("March 17-18 (cancelled) Meeting - 2020", "cancelled"),
    ("March 25 Conference Call - 2003", "conference_call"),
    ("August 22 (notation vote)", "notation_vote"),
])
def test_classify_event(label, etype):
    assert classify_event(label) == etype


def test_parse_release_date_variants():
    assert parse_release_date("Minutes (Released March 29, 1996)") == date(1996, 3, 29)
    assert parse_release_date("Minutes (Released Feb 20, 2008): HTML") == date(2008, 2, 20)
    assert parse_release_date("no date here") is None


def test_statement_date_from_url():
    assert statement_date_from_url("/newsevents/pressreleases/monetary20250129a.htm") == date(2025, 1, 29)
    assert statement_date_from_url("/boarddocs/press/general/2000/20000202/") == date(2000, 2, 2)
    assert statement_date_from_url(None) is None


HISTORICAL = """
<div class="panel panel-default"><div class="panel-heading"><h5>January 30-31 Meeting - 1996</h5></div>
<div class="row"><p><a href="/fomc/19960131DEFAULT.htm">Statement</a></p>
<p><a href="/fomc/minutes/19960130.htm">Minutes</a> (Released March 29, 1996)</p></div></div>
<div class="panel panel-default"><h5 class="panel-heading">March 25 Conference Call - 1996</h5>
<div class="row"><p><a href="/fomc/minutes/19960130.htm#x">Minutes</a></p></div></div>
"""


def test_parse_historical_year():
    rows = parse_historical_year(HISTORICAL, 1996, "p")
    assert [r.event_type for r in rows] == ["scheduled", "conference_call"]
    first, call = rows
    assert first.meeting_end == date(1996, 1, 31)
    assert first.statement_url == "/fomc/19960131DEFAULT.htm"
    assert first.minutes_url == "/fomc/minutes/19960130.htm"
    assert first.minutes_release_date == date(1996, 3, 29)
    # links into another meeting's minutes (with '#') are not this event's minutes
    assert call.minutes_url is None and not call.scheduled


RECENT = """
<div class="panel panel-default"><div class="panel-heading"><h4><a>2025 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting"><div class="fomc-meeting__month"><strong>Apr/May</strong></div>
<div class="fomc-meeting__date">30-1</div>
<div><a href="/newsevents/pressreleases/monetary20250501a.htm">HTML</a></div>
<div class="fomc-meeting__minutes"><a href="/monetarypolicy/fomcminutes20250501.htm">HTML</a>
<br> (Released May 21, 2025)</div></div>
<div class="row fomc-meeting"><div class="fomc-meeting__month"><strong>August</strong></div>
<div class="fomc-meeting__date">22 (notation vote)</div></div>
</div>
"""


def test_parse_recent_calendar():
    rows = parse_recent_calendar(RECENT, "p")
    assert len(rows) == 2
    assert rows[0].meeting_end == date(2025, 5, 1) and rows[0].scheduled
    assert rows[0].minutes_release_date == date(2025, 5, 21)
    assert rows[1].event_type == "notation_vote" and not rows[1].scheduled


# --- http cache -----------------------------------------------------------------

def test_cache_path_and_decode(tmp_path):
    p = cache_path("https://www.federalreserve.gov/fomc/minutes/19960130.htm", tmp_path)
    assert p.name == "fomc_minutes_19960130.htm"
    assert decode_body("café".encode("utf-8")) == "café"
    assert decode_body("“q”".encode("cp1252")) == "“q”"


# --- html extraction and cleaning -----------------------------------------------

OLD_STATEMENT = """<html><body><i>Release Date: January 29, 2003</i><p>
<font>For immediate release</font><p>The Federal Open Market Committee decided today
to keep its target for the federal funds rate unchanged at 1-1/4 percent.<p>
In taking the discount action, the Board approved requests submitted by the Boards of
Directors of the Federal Reserve Banks of New York and Dallas. Inflation remains low.
<p>Voting for the FOMC monetary policy action were Alan Greenspan, Chairman; and others.
<p><a href="/x">2003 Monetary policy</a><hr>Last update: January 29, 2003</body></html>"""

NEW_STATEMENT = """<html><body><nav>Menu stuff here</nav><div id="article">
<div class="heading"><p>January 29, 2025</p><h3>Federal Reserve issues FOMC statement</h3>
<p>For release at 2:00 p.m. EST</p><p>Share</p></div>
<div><p>Recent indicators suggest that economic activity has continued to expand at a solid pace.</p>
<p>Voting for the monetary policy action were Jerome H. Powell, Chair; John C. Williams.</p>
<p>For media inquiries, please email media@example.org or call 202-452-2955.</p>
<p>Implementation Note issued January 29, 2025</p></div></div></body></html>"""


def test_html_to_paragraphs_reflows_hard_wrapped_text():
    paras = html_to_paragraphs(OLD_STATEMENT)
    assert ("The Federal Open Market Committee decided today to keep its target for the "
            "federal funds rate unchanged at 1-1/4 percent.") in paras


def test_html_to_paragraphs_prefers_article():
    paras = html_to_paragraphs(NEW_STATEMENT)
    assert "Menu stuff here" not in paras
    assert paras[0] == "January 29, 2025"


def test_clean_statement_old_layout():
    res = clean_statement(html_to_paragraphs(OLD_STATEMENT))
    assert res.kept == [
        "The Federal Open Market Committee decided today to keep its target for the federal "
        "funds rate unchanged at 1-1/4 percent.",
        "Inflation remains low.",
    ]
    rules = {r for r, _ in res.stripped}
    assert {"header", "footer", "voting", "discount_approval"} <= rules


def test_clean_statement_new_layout():
    res = clean_statement(html_to_paragraphs(NEW_STATEMENT))
    assert res.kept == ["Recent indicators suggest that economic activity has continued to "
                        "expand at a solid pace."]
    rules = [r for r, _ in res.stripped]
    assert "media_contact" in rules and "voting" in rules and "footer" in rules


MINUTES = [
    "Minutes of the Federal Open Market Committee",
    "A meeting of the Federal Open Market Committee was held in the offices of the Board.",
    "Present:", "Mr. Greenspan, Chairman",
    "By unanimous vote, the minutes of the meeting held on December 19 were approved and more words.",
    "The Manager of the System Open Market Account reported on recent developments in foreign exchange markets and more.",
    "Participants noted that inflation pressures had increased somewhat over the intermeeting period overall.",
    "The vote encompassed approval of the statement below to be released at 2:15 p.m.:",
    "“The Federal Open Market Committee decided today to raise its target.",
    "The Committee judges that risks are balanced.”",
    "Votes for this action:", "Messrs. Bernanke, Geithner, and Kohn.",
    "Votes against this action:", "None.",
    "Participants also discussed the balance sheet at length and agreed to revisit the topic soon.",
    "It was agreed that the next meeting of the Committee would be held on Tuesday, March 18.",
    "The meeting adjourned at 1:15 p.m.",
]


def test_clean_minutes():
    res = clean_minutes(MINUTES)
    assert res.kept == [MINUTES[5], MINUTES[6], MINUTES[7], MINUTES[14]]
    by_rule = {}
    for r, t in res.stripped:
        by_rule.setdefault(r, []).append(t)
    assert len(by_rule["quoted_statement_or_directive"]) == 2
    assert "None." in by_rule["voting"]
    assert MINUTES[-1] in by_rule["tail"]
    assert "Present:" in by_rule["header_attendance"] + by_rule["procedural"]


def test_clean_minutes_keeps_special_topics_before_markets_report():
    paras = [
        "A joint meeting of the Federal Open Market Committee and the Board of Governors was held.",
        "Jerome H. Powell, Chair; John C. Williams, Vice Chair; Michael S. Barr; Michelle W. Bowman",
        "In the agenda for this meeting, it was reported that advices of the election of members had been received.",
        "iii. Subject to reasonable limitations on the amount of Eligible Securities that each borrower may borrow.",
        "The Manager shall clear with the Subcommittee any operation that is not routine in character.",
        "The maximum level of employment is a broad-based and inclusive goal that is not directly measurable.",
        "Participants discussed the balance sheet at length, and many noted that runoff could end earlier than expected.",
        "Developments in Financial Markets and Open Market Operations",
        "The manager turned first to a review of domestic financial market developments over the period.",
        "It was agreed that the next meeting of the Committee would be held on Tuesday.",
    ]
    res = clean_minutes(paras)
    assert res.kept == [paras[6], paras[8]]
    rules = dict((t, r) for r, t in res.stripped)
    assert rules[paras[1]] == "header_attendance"
    assert rules[paras[3]] == rules[paras[4]] == "header_organisational"
    assert rules[paras[5]] == "longer_run_goals_statement"
    assert rules[paras[7]] == "heading"


def test_statement_release_time_sources():
    assert release_time_from_statement_page(["For release at 2:00 p.m. EST"]) == time(14, 0)
    assert statement_times_in_minutes(MINUTES) == [time(14, 15)]
    # a mention of another day's statement is ignored
    other = ["the statement to be released at 8:30 a.m. on Tuesday, January 22"]
    assert statement_times_in_minutes(other) == []
    rt = resolve_statement_time(["For immediate release"], MINUTES)
    assert (rt.time, rt.source) == (time(14, 15), "minutes")
    rt = resolve_statement_time(["For immediate release"], None)
    assert rt.time is None and rt.source == "unverified"


# --- sentence splitting ---------------------------------------------------------

def test_split_sentences_handles_abbreviations():
    text = ("Mr. Hoenig dissented. The U.S. economy grew at a 2.5 percent rate. "
            "Janet L. Yellen, Vice Chair, spoke at 2:15 p.m. on Jan. 5. Growth slowed.")
    assert split_sentences(text) == [
        "Mr. Hoenig dissented.",
        "The U.S. economy grew at a 2.5 percent rate.",
        "Janet L. Yellen, Vice Chair, spoke at 2:15 p.m. on Jan. 5.",
        "Growth slowed.",
    ]


def test_split_sentences_quotes_and_empty():
    assert split_sentences("") == []
    assert split_sentences("“Rates rose.” Then prices fell.") == [
        "“Rates rose.”", "Then prices fell."]
