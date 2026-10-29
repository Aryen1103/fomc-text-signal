# Tone validation set

Chooses the primary tone scorer for phase 3 on evidence rather than by
preference. Written, sampled and labelled **before any scorer was run**, and
before any returns were examined.

## Sample

`statement_sentences.jsonl`: 150 sentences, one from each of 150 randomly
chosen scheduled statements (seed 20261029, `scripts/sample_validation.py`),
1994–2026. Boilerplate that repeats across statements is kept, because the
scorers see it too.

## Labelling guide

Each sentence is labelled from its own text only, without the surrounding
statement, the decision taken, or market context. The scheme follows the
sentence-level hawkish/dovish convention of Shah, Paturi and Chava (2023,
"Trillion Dollar Words").

| Label | The sentence... |
|---|---|
| `hawkish` | signals or supports tighter policy: rate or discount-rate increases, firming, removing accommodation, ending or tapering asset purchases, balance-sheet reduction; upside inflation risk or elevated inflation; strong or improving activity and labour markets |
| `dovish` | signals or supports easier policy: cuts, accommodation, asset purchases, low rates for an extended period, patience; weak or deteriorating activity, slack, financial strain, downside risks; inflation low, falling or below goal |
| `neutral` | carries no direction: unchanged-rate announcements without a stated bias, balanced risks, monitoring and data-dependence language, mandate boilerplate, definitions and operational detail, or two opposing clauses of similar weight |

For "X, but Y" and "although X, Y" sentences the label follows the main clause
(Y). A historical description of a past action is neutral.

Labels are from a single annotator, so there is no inter-annotator agreement
figure; borderline calls are noted in the `note` field.

## Selection rule (fixed before scoring)

1. Every candidate scorer labels each sentence `hawkish`, `dovish` or `neutral`.
   Candidates: the lexicon baseline, zero-shot DeBERTa-v3-base and
   zero-shot DeBERTa-v3-large (MoritzLaurer `*-zeroshot-v2.0`).
2. The primary scorer is the one with the highest **macro-F1** over the three
   classes. Accuracy and Cohen's kappa are reported alongside.
3. If two candidates are within 0.03 macro-F1, the cheaper one wins
   (lexicon < base < large).
4. The scorers' settings (word lists, hypothesis wording) are fixed before
   they are run on this set and are not changed afterwards. Results for every
   candidate are reported, including the ones not chosen.

## Document score (fixed before scoring)

For a document with N scored sentences, H labelled hawkish and D dovish:
`score = (H - D) / N`, in [-1, 1]. `tone_change` (README, H1) is the score
minus the score of the previous scheduled document of the same type. The same
formula is used for every scorer.
