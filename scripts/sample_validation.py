"""Draw the validation sentences used to choose the primary tone scorer (phase 2).

One sentence from each of 150 randomly chosen scheduled statements (seeded), so
no single statement dominates. Labels are added by hand to the output file
before any scorer is run on it; see validation/README.md.

    python scripts/sample_validation.py
"""

from __future__ import annotations

import json
import random

import polars as pl

from fomc_signal.paths import PROCESSED, ROOT
from fomc_signal.score.sentences import split_sentences

SEED = 20261029
N_SENTENCES = 150
OUT = ROOT / "validation" / "statement_sentences.jsonl"


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; it may hold labels. Remove it deliberately to resample.")
    docs = (pl.read_parquet(PROCESSED / "documents.parquet")
            .filter((pl.col("doc_type") == "statement") & pl.col("scheduled"))
            .sort("release_date"))
    rng = random.Random(SEED)
    rows = docs.select("doc_id", "release_date", "clean_text").rows(named=True)
    picked = sorted(rng.sample(rows, N_SENTENCES), key=lambda r: r["release_date"])
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for i, row in enumerate(picked, start=1):
            sentence = rng.choice(split_sentences(row["clean_text"]))
            f.write(json.dumps({"id": f"v{i:03d}", "doc_id": row["doc_id"],
                                "release_date": row["release_date"].isoformat(),
                                "sentence": sentence, "label": None}, ensure_ascii=False) + "\n")
    print(f"{N_SENTENCES} sentences from {N_SENTENCES} statements -> {OUT}")


if __name__ == "__main__":
    main()
