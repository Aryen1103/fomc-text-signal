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

_Counts and gaps: see the phase 1 checkpoint section below._

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
