"""Phase 2 sanity checks on statement tone scores. Uses no market data.

  python scripts/check_tone.py --scorer zs-large

1. Decision check: statements that raise rates should score more hawkish than
   those that hold, and those more than cuts. The decision is read from the
   statement's own wording, not from market or rate data.
2. Scorer agreement: correlation of document scores with the lexicon baseline.
3. Time series: results/phase2/statement_tone_<scorer>.png, for comparison with
   known episodes (2004-06 and 2022-23 hiking, 2001 and 2008 easing).
Writes results/phase2/statement_checks_<scorer>.json.
"""

from __future__ import annotations

import argparse
import json
import re

import matplotlib
import numpy as np
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from fomc_signal.paths import PROCESSED, RESULTS  # noqa: E402

_RAISE = re.compile(r"\b(decided|voted|agreed)\b[^.]{0,80}\b(raise|increase|firm)", re.I)
_LOWER = re.compile(r"\b(decided|voted|agreed)\b[^.]{0,80}\b(lower|reduce|cut|ease)", re.I)
_HOLD = re.compile(r"\b(decided|voted|agreed)\b[^.]{0,80}\b(maintain|keep|leave)", re.I)


def decision(text: str) -> str:
    """raise / lower / hold / unclear, from the first decision sentence of a statement."""
    for sentence in re.split(r"(?<=\.)\s+", text):
        if _RAISE.search(sentence):
            return "raise"
        if _LOWER.search(sentence):
            return "lower"
        if _HOLD.search(sentence):
            return "hold"
    return "unclear"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scorer", default="zs-large")
    args = ap.parse_args()
    docs = pl.read_parquet(PROCESSED / "documents.parquet").select("doc_id", "clean_text")
    tone = (pl.read_parquet(PROCESSED / f"tone_{args.scorer}_statement.parquet")
            .filter(pl.col("scheduled")).join(docs, on="doc_id"))
    tone = tone.with_columns(pl.col("clean_text").map_elements(decision, return_dtype=pl.String).alias("decision"))
    by_decision = (tone.group_by("decision").agg(pl.len().alias("n"), pl.col("score").mean().round(3).alias("mean_score"))
                   .sort("mean_score"))
    lex = pl.read_parquet(PROCESSED / "tone_lexicon_statement.parquet").select("doc_id", pl.col("score").alias("lexicon"))
    joined = tone.join(lex, on="doc_id")
    corr_level = float(np.corrcoef(joined["score"], joined["lexicon"])[0, 1])
    changes = joined.drop_nulls("tone_change").sort("release_date").with_columns(
        (pl.col("lexicon") - pl.col("lexicon").shift(1)).alias("lexicon_change")).drop_nulls("lexicon_change")
    corr_change = float(np.corrcoef(changes["tone_change"], changes["lexicon_change"])[0, 1])

    out = RESULTS / "phase2"
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 3.6))
    colors = {"raise": "#c0392b", "lower": "#2471a3", "hold": "#7f8c8d", "unclear": "#bbbbbb"}
    for d, c in colors.items():
        part = tone.filter(pl.col("decision") == d)
        ax.scatter(part["release_date"], part["score"], s=14, color=c, label=f"{d} ({part.height})", zorder=3)
    ax.plot(tone["release_date"], tone["score"], color="#555555", lw=0.6, zorder=2)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_ylabel("tone (H - D) / N")
    ax.set_title(f"Scheduled FOMC statement tone, {args.scorer} (positive = hawkish)")
    ax.legend(loc="lower left", fontsize=8, ncol=4, frameon=False)
    fig.tight_layout()
    fig.savefig(out / f"statement_tone_{args.scorer}.png", dpi=150)

    result = {"scorer": args.scorer, "statements": tone.height,
              "mean_score_by_decision": by_decision.to_dicts(),
              "corr_with_lexicon_level": round(corr_level, 3), "corr_with_lexicon_change": round(corr_change, 3)}
    (out / f"statement_checks_{args.scorer}.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
