"""Agreement metrics for the validation set (plain Python; scikit-learn is not a dependency)."""

from __future__ import annotations

LABELS = ("hawkish", "dovish", "neutral")


def confusion(gold: list[str], pred: list[str]) -> dict[str, dict[str, int]]:
    """counts[gold][pred]."""
    counts = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in zip(gold, pred, strict=True):
        counts[g][p] += 1
    return counts


def macro_f1(gold: list[str], pred: list[str]) -> float:
    c = confusion(gold, pred)
    f1s = []
    for label in LABELS:
        tp = c[label][label]
        fp = sum(c[g][label] for g in LABELS) - tp
        fn = sum(c[label].values()) - tp
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s)


def accuracy(gold: list[str], pred: list[str]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold)


def cohen_kappa(gold: list[str], pred: list[str]) -> float:
    n = len(gold)
    observed = accuracy(gold, pred)
    expected = sum((gold.count(label) / n) * (pred.count(label) / n) for label in LABELS)
    return 0.0 if expected == 1 else (observed - expected) / (1 - expected)
