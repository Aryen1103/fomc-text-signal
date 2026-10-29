"""Phase 2 entry point: tone scoring.

  python scripts/score.py --validate                          # every candidate on validation/
  python scripts/score.py --documents statement --scorer lexicon

--validate writes results/phase2/validation_*.{csv,json} and applies the
selection rule in validation/README.md. --documents writes one row per document
(sentence counts, score = (H - D) / N, tone_change against the previous
scheduled document of the same type) to data/processed/tone_<scorer>_<type>.parquet,
and the sentence labels alongside. Zero-shot scorers need torch and
transformers, which run in Docker on the development machine (see README).
"""

from __future__ import annotations

import argparse
import json

import polars as pl

from fomc_signal.paths import PROCESSED, RESULTS, ROOT
from fomc_signal.score import lexicon, metrics
from fomc_signal.score.sentences import split_sentences

CANDIDATES = ["lexicon", "zs-base", "zs-large"]  # cheapest first: the tie-break order
TIE_MARGIN = 0.03
VALIDATION = ROOT / "validation" / "statement_sentences.jsonl"
OUT = RESULTS / "phase2"


def scorer(name: str):
    """A function: list of sentences -> list of labels."""
    if name == "lexicon":
        return lambda sentences: [lexicon.label(s) for s in sentences]
    from fomc_signal.score.zeroshot import ZeroShotScorer

    model = ZeroShotScorer(name)
    return lambda sentences: model.score(sentences)[0]


def choose(results: dict[str, dict]) -> str:
    """Selection rule: best macro-F1; within TIE_MARGIN of the best, the cheapest candidate wins."""
    best = max(r["macro_f1"] for r in results.values())
    return next(name for name in CANDIDATES if name in results and results[name]["macro_f1"] >= best - TIE_MARGIN)


def validate(names: list[str]) -> None:
    rows = [json.loads(line) for line in VALIDATION.read_text(encoding="utf-8").splitlines() if line.strip()]
    sentences, gold = [r["sentence"] for r in rows], [r["label"] for r in rows]
    OUT.mkdir(parents=True, exist_ok=True)
    results, preds = {}, {}
    for name in names:
        preds[name] = scorer(name)(sentences)
        results[name] = {"macro_f1": round(metrics.macro_f1(gold, preds[name]), 4),
                         "accuracy": round(metrics.accuracy(gold, preds[name]), 4),
                         "kappa": round(metrics.cohen_kappa(gold, preds[name]), 4),
                         "confusion_gold_by_pred": metrics.confusion(gold, preds[name])}
        print(f"{name:<9} macro-F1 {results[name]['macro_f1']:.3f}  accuracy {results[name]['accuracy']:.3f}  "
              f"kappa {results[name]['kappa']:.3f}")
    table = pl.DataFrame({"id": [r["id"] for r in rows], "gold": gold, "sentence": sentences,
                          **{f"pred_{n}": p for n, p in preds.items()}})
    table.write_csv(OUT / "validation_predictions.csv")
    summary = {"candidates": results, "majority_class_accuracy": max(gold.count(x) for x in set(gold)) / len(gold)}
    if set(CANDIDATES) <= set(results):
        summary["primary"] = choose(results)
        print(f"primary scorer by the pre-registered rule: {summary['primary']}")
    (OUT / "validation_metrics.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def score_documents(doc_type: str, name: str) -> None:
    docs = (pl.read_parquet(PROCESSED / "documents.parquet").filter(pl.col("doc_type") == doc_type)
            .sort("release_date"))
    label = scorer(name)
    sentence_rows, doc_rows = [], []
    for doc in docs.iter_rows(named=True):
        sents = split_sentences(doc["clean_text"] or "")
        labels = label(sents) if sents else []
        sentence_rows += [{"doc_id": doc["doc_id"], "i": i, "sentence": s, "label": lab}
                          for i, (s, lab) in enumerate(zip(sents, labels))]
        h, d = labels.count("hawkish"), labels.count("dovish")
        doc_rows.append({"doc_id": doc["doc_id"], "release_date": doc["release_date"], "scheduled": doc["scheduled"],
                         "n_sentences": len(sents), "n_hawkish": h, "n_dovish": d,
                         "score": (h - d) / len(sents) if sents else None})
    out = pl.DataFrame(doc_rows)
    # tone_change: against the previous *scheduled* document of the same type (README, H1).
    sched = (out.filter(pl.col("scheduled")).sort("release_date")
             .with_columns((pl.col("score") - pl.col("score").shift(1)).alias("tone_change")))
    out = out.join(sched.select("doc_id", "tone_change"), on="doc_id", how="left")
    out.write_parquet(PROCESSED / f"tone_{name}_{doc_type}.parquet")
    pl.DataFrame(sentence_rows).write_parquet(PROCESSED / f"tone_{name}_{doc_type}_sentences.parquet")
    print(f"{doc_type}: {out.height} documents, {len(sentence_rows)} sentences scored with {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--candidates", nargs="+", default=CANDIDATES, choices=CANDIDATES)
    ap.add_argument("--documents", choices=["statement", "minutes"])
    ap.add_argument("--scorer", choices=CANDIDATES)
    args = ap.parse_args()
    if args.validate:
        validate(args.candidates)
    elif args.documents and args.scorer:
        score_documents(args.documents, args.scorer)
    else:
        ap.error("use --validate, or --documents TYPE --scorer NAME")


if __name__ == "__main__":
    main()
