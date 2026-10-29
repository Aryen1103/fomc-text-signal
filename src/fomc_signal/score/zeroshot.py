"""Zero-shot NLI tone scorer (MoritzLaurer DeBERTa-v3 zeroshot-v2.0 models).

Each sentence is paired with one hypothesis per label; the label whose
hypothesis gets the highest entailment logit wins (softmax over the three
entailment logits, as in the Hugging Face zero-shot pipeline). The hypothesis
wording mirrors the labelling guide and is fixed before the scorer is run on
the validation set (validation/README.md). torch and transformers are imported
lazily, so the rest of the package and the tests run without them.
"""

from __future__ import annotations

from collections.abc import Iterable

MODELS = {
    "zs-base": "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
    "zs-large": "MoritzLaurer/deberta-v3-large-zeroshot-v2.0",
}
HYPOTHESES = {
    "hawkish": "This text signals tighter monetary policy, rising inflation, or a strengthening economy.",
    "dovish": "This text signals easier monetary policy, falling inflation, or a weakening economy.",
    "neutral": "This text gives no signal about the direction of monetary policy or the economy.",
}
LABELS = list(HYPOTHESES)
MAX_TOKENS = 256
BATCH_SIZE = 16


def entailment_index(id2label: dict) -> int:
    """Position of the entailment class in the model's output."""
    for i, name in id2label.items():
        if str(name).lower().startswith("entail"):
            return int(i)
    raise ValueError(f"no entailment label in {id2label}")


def labels_from_logits(rows: Iterable[list[float]]) -> tuple[list[str], list[list[float]]]:
    """Argmax label and softmax probabilities from per-sentence entailment logits (one per label)."""
    import math

    labels, probs = [], []
    for logits in rows:
        top = max(logits)
        exp = [math.exp(x - top) for x in logits]
        total = sum(exp)
        p = [e / total for e in exp]
        probs.append(p)
        labels.append(LABELS[p.index(max(p))])
    return labels, probs


class ZeroShotScorer:
    def __init__(self, name: str, cache_dir: str | None = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.name, self.model_id = name, MODELS[name]
        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, cache_dir=cache_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_id, cache_dir=cache_dir).eval()
        self.entail = entailment_index(self.model.config.id2label)

    def score(self, sentences: list[str]) -> tuple[list[str], list[list[float]]]:
        """Label and [p_hawkish, p_dovish, p_neutral] for each sentence."""
        pairs = [(s, HYPOTHESES[label]) for s in sentences for label in LABELS]
        logits: list[float] = []
        for start in range(0, len(pairs), BATCH_SIZE * len(LABELS)):
            chunk = pairs[start: start + BATCH_SIZE * len(LABELS)]
            batch = self.tokenizer([p for p, _ in chunk], [h for _, h in chunk], padding=True,
                                   truncation="only_first", max_length=MAX_TOKENS, return_tensors="pt")
            with self._torch.no_grad():
                logits += self.model(**batch).logits[:, self.entail].tolist()
        rows = [logits[i: i + len(LABELS)] for i in range(0, len(logits), len(LABELS))]
        return labels_from_logits(rows)
