# fomc-text-signal

Does the *change* in hawkish/dovish tone of FOMC statements, scored by a local
transformer model, predict market reactions, after controlling for the rate
decision itself?

This is a research project, not a trading system. A weak or null result, tested
carefully, is an acceptable outcome, and results are reported as found.

**Status:** Phase 1 (ingestion) complete. Phases 2 (tone scoring) and 3 (event study) not started.
No returns have been looked at.

## Pre-registered design

Fixed before any returns were examined. No horizons or assets are added after seeing results.

| | |
|---|---|
| **H1** | A more hawkish statement than the previous one (positive tone change) is followed by lower equity returns (SPY) and lower Treasury returns (TLT, i.e. higher yields). |
| **H2** | The effect is concentrated on the announcement day and decays over later horizons. |
| **H3** | Minutes (released ~3 weeks later) carry a weaker signal than statements, because the market has already priced most of the decision. |
| Key variable | `tone_change = score(t) - score(previous statement)` |
| Daily horizons | day 0 (close before release to close on release day), day 1, day 5 cumulative; log returns |
| Outcomes | SPY return, TLT return, change in 2-year Treasury yield (FRED `DGS2`) |
| Regression | `return = a + b1 * tone_change + b2 * rate_change + e`, HC1 standard errors |
| Multiple testing | 3 horizons x 3 outcomes = 9 tests per document type, Holm correction; raw and adjusted p-values reported |
| Out-of-sample split | by date, chosen before phase 3 is run (recorded here before running) |
| Intraday (optional) | release to +5 min and +60 min, only if a free/cheap intraday source exists |

## Data (phase 1)

Scraped from federalreserve.gov: the current calendar page
(`/monetarypolicy/fomccalendars.htm`, 2021 onward) and the per-year archive pages
(`/monetarypolicy/fomchistoricalYYYY.htm`, 1994-2020). Raw HTML is cached in
`data/cache/html/` and never re-downloaded; requests are rate limited.

### What was collected (as of 2026-09-28)

| | Scheduled | Unscheduled (flagged, excluded from main test) | Release dates |
|---|---|---|---|
| Statements | 231 | 19 | 1994-02-04 to 2026-09-16 |
| Minutes | 260 | 1 | 1994-03-25 to 2026-08-19 |

Gaps, all genuine rather than scraping failures:

- **1994 to March 1999:** the FOMC issued a statement only when it changed policy, so 30
  scheduled meetings in that period have no statement. Every scheduled meeting from
  May 1999 on has one.
- **15 September 2003** was a meeting with no statement and no separate minutes.
- **Minutes timing changed in December 2004.** Before 2005, minutes were released after
  the next meeting (median 50 days after the meeting); from 2005 on, about three weeks
  later (median 21 days). H3 therefore uses minutes released from 2005 onward (173 documents).
- **TLT starts on 2002-07-30**, which limits the daily event study to 193 scheduled
  statements. That is a small sample.

Unscheduled actions (conference calls, unscheduled meetings, notation votes, and the
cancelled March 2020 meeting) are kept in the data with `scheduled = false`.

### Release times

The time is verified per document and never assumed. When it cannot be verified it is
left null.

| Document | Source of time | Count |
|---|---|---|
| Statement | "For release at ..." on the statement page (2013 on, plus unscheduled actions) | 95 |
| Statement | the meeting's minutes ("statement ... to be released at 2:15 p.m."), 2006-2013 | 76 |
| Statement | unverified (1994-2005: neither source states a time) | 79 |
| Minutes | "For release at ..." on the minutes press release | 163 |
| Minutes | unverified (mostly pre-2005; no press release in the archive) | 98 |

Verified times vary: 2:15 pm ET through 2012, 12:30 pm on 2011-12 press-conference
days, 2:00 pm from 2013. The March 2013 minutes were released at 9:00 am on 2013-04-10
after an early leak. One minutes press release (2008-01-02) prints "12:00 a.m.". That
is treated as implausible and left unverified. Unverified times do not affect the
daily (close-to-close) study. They only matter for the optional intraday phase.

The statement dated 2007-06-28 is hosted at a URL stamped 20070618. The date printed on
the page is used, and the discrepancy is recorded in `release_date_check`.

### Cleaning

Cleaning is rule based and works on paragraphs. Every removed paragraph or sentence is
saved with the rule that removed it, in `data/processed/stripped.parquet`.

- **Statements:** page header ("For release at ...", date, title), footer and links,
  voting lists (including dissent notes), media contacts, and the procedural sentence
  "the Board approved requests submitted by the Boards of Directors of ...".
- **Minutes:** attendance lists and organisational/legal text (authorizations,
  elections, rules) before the markets report, and quoted statement and directive text,
  so the minutes score does not re-score the statement. Also removed: voting blocks, the
  annually re-adopted Statement on Longer-Run Goals, section headings, and everything from
  "It was agreed that the next meeting ..." on. Special-topic discussions placed before
  the markets report (framework reviews, balance-sheet normalization) are kept.

After cleaning, statements have a median of 279 words (36 to 808) and minutes a median
of 5,350 words.

## Repo layout

```
src/fomc_signal/ingest/   scraper (cached), calendar parser, HTML extraction, cleaning
src/fomc_signal/score/    lexicon baseline, zero-shot NLI, supervised (phase 2)
src/fomc_signal/market/   price and yield loaders, returns (phase 3)
src/fomc_signal/study/    regressions, bootstrap, placebo, multiple testing (phase 3)
src/fomc_signal/report/   tables and figures
scripts/                  ingest.py, score.py, study.py, report.py
tests/                    pytest, no network
results/                  generated tables and figures
```

## Running

```bash
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -r requirements-dev.txt && pip install -e .
python scripts/ingest.py                            # phase 1
python -m pytest
```
