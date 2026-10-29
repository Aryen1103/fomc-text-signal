import pytest

from fomc_signal.score import lexicon
from fomc_signal.score.zeroshot import LABELS, entailment_index, labels_from_logits


@pytest.mark.parametrize("sentence, expected", [
    ("Inflation remains elevated.", "hawkish"),
    ("The unemployment rate remains elevated.", "dovish"),
    ("The Committee decided today to raise its target for the federal funds rate by 25 basis points.", "hawkish"),
    ("The Committee decided today to lower its target for the federal funds rate by 50 basis points.", "dovish"),
    ("Economic activity remains soft.", "dovish"),
    ("Some further policy firming may be needed.", "hawkish"),
    ("The Committee will start removing policy accommodation next year.", "hawkish"),
    ("Policy remains highly accommodative.", "dovish"),
    ("Low levels of the federal funds rate are likely to be warranted for an extended period.", "dovish"),
    ("Consistent with its statutory mandate, the Committee seeks to foster maximum employment.", "neutral"),
])
def test_lexicon_direction_depends_on_the_subject(sentence, expected):
    assert lexicon.label(sentence) == expected


def test_entailment_index_reads_the_model_config():
    assert entailment_index({0: "entailment", 1: "not_entailment"}) == 0
    assert entailment_index({"0": "contradiction", "1": "neutral", "2": "entailment"}) == 2
    with pytest.raises(ValueError):
        entailment_index({0: "positive", 1: "negative"})


def test_zero_shot_label_is_the_hypothesis_with_the_highest_entailment():
    labels, probs = labels_from_logits([[3.0, 0.0, 1.0], [0.0, 0.0, 5.0]])
    assert labels == [LABELS[0], LABELS[2]] == ["hawkish", "neutral"]
    assert all(abs(sum(p) - 1) < 1e-9 for p in probs)


def test_metrics_on_a_known_case():
    from fomc_signal.score import metrics

    gold = ["hawkish", "hawkish", "dovish", "neutral"]
    pred = ["hawkish", "dovish", "dovish", "neutral"]
    assert metrics.accuracy(gold, pred) == 0.75
    # F1: hawkish 2/3, dovish 2/3, neutral 1
    assert abs(metrics.macro_f1(gold, pred) - (2 / 3 + 2 / 3 + 1) / 3) < 1e-9
    assert metrics.cohen_kappa(gold, gold) == 1.0


def test_selection_rule_prefers_the_cheaper_scorer_within_the_margin():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("score_script", Path(__file__).parents[1] / "scripts" / "score.py")
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    results = {"lexicon": {"macro_f1": 0.50}, "zs-base": {"macro_f1": 0.70}, "zs-large": {"macro_f1": 0.72}}
    assert score.choose(results) == "zs-base"
    results["zs-large"]["macro_f1"] = 0.80
    assert score.choose(results) == "zs-large"
