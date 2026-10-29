"""Lexicon baseline tone scorer: transparent, no model.

A sentence's tone comes from (subject, direction) pairs and from policy phrases.
"Elevated" means opposite things next to "inflation" and "unemployment", so a
direction word only counts next to a subject (within WINDOW tokens), and the
pair's sign is subject sign x direction sign:

    inflation (+1) x elevated (+1)   -> hawkish
    unemployment (-1) x elevated (+1) -> dovish
    activity (+1) x weak (-1)         -> dovish

Policy phrases carry their own sign ("further firming", "extended period").
Sentence label: positive total = hawkish, negative = dovish, zero = neutral.
The lists are fixed before the scorer is run on the validation set
(validation/README.md) and are not tuned on it.
"""

from __future__ import annotations

import re

WINDOW = 4

# Subjects: +1 when "more" of it is hawkish, -1 when "more" of it is dovish.
SUBJECTS = {
    "inflation": 1, "prices": 1, "price": 1, "wages": 1, "costs": 1, "pressures": 1,
    "rate": 1, "rates": 1, "target": 1,  # the policy rate: raising it is hawkish
    "activity": 1, "growth": 1, "economy": 1, "expansion": 1, "spending": 1, "investment": 1,
    "output": 1, "production": 1, "employment": 1, "jobs": 1, "job": 1, "hiring": 1, "demand": 1,
    "labor": 1, "conditions": 1, "recovery": 1, "sales": 1, "housing": 1, "utilization": 1,
    "unemployment": -1, "slack": -1, "underutilization": -1, "losses": -1, "strains": -1,
}

# Direction words: +1 = more / stronger / up, -1 = less / weaker / down.
DIRECTIONS = {
    **dict.fromkeys(["increase", "increased", "increases", "increasing", "raise", "raised", "raising",
                     "rise", "rising", "rose", "higher", "high", "elevated", "strong", "stronger", "solid",
                     "robust", "firm", "firmed", "firming", "accelerate", "accelerated", "accelerating",
                     "improve", "improved", "improving", "improvement", "strengthen", "strengthened",
                     "expand", "expanded", "expanding", "picked", "upward", "heightened", "tight",
                     "tighter"], 1),
    **dict.fromkeys(["decrease", "decreased", "decline", "declined", "declining", "lower", "lowered",
                     "low", "reduce", "reduced", "reduction", "cut", "weak", "weaker", "weakened", "soft",
                     "softened", "slow", "slowed", "slowing", "slower", "subdued", "muted", "depressed",
                     "below", "contained", "eased", "easing", "diminished", "diminish", "moderated",
                     "sluggish", "downward", "fall", "fell", "falling"], -1),
}

# Policy phrases with their own sign, matched on the lower-cased sentence.
REMOVING_ACCOMMODATION = re.compile(r"\b(remov(e|ing|al of)|withdraw\w*) (policy )?accommodation\b|\bless accommodative\b")
ACCOMMODATION = re.compile(r"\baccommodat(ive|ion)\b")  # dovish, unless it is being removed
# "rate" is the policy rate except in these compounds.
NOT_POLICY_RATE = {"unemployment", "inflation", "participation", "savings", "exchange", "growth"}
PHRASES = [(re.compile(p), s) for p, s in [
    (r"\bfirming\b", 1), (r"\btighten(ing|ed)?\b", 1), (r"\brestrictive\b", 1),
    (r"\breduc\w* (in )?the (monthly )?pace of (its )?(net )?(asset )?purchases\b", 1),
    (r"\bnormaliz\w*\b", 1), (r"\binflation risks?\b", 1), (r"\bease the stance\b", -1),
    (r"\b(asset|securities) purchases\b", -1), (r"\bpurchas(e|ing) (additional )?(agency|longer-term|treasury)\b", -1),
    (r"\bexceptionally low\b", -1), (r"\bextended period\b", -1), (r"\bconsiderable (period|time)\b", -1),
    (r"\bpatient\b", -1), (r"\bdownside risks?\b", -1),
]]
_TOKEN = re.compile(r"[a-z]+")


def sentence_score(sentence: str) -> int:
    """Signed tone count for one sentence."""
    s = sentence.lower()
    tokens = _TOKEN.findall(s)
    total = sum(sign for pattern, sign in PHRASES if pattern.search(s))
    total += 1 if REMOVING_ACCOMMODATION.search(s) else -1 if ACCOMMODATION.search(s) else 0
    for i, tok in enumerate(tokens):
        if tok in ("rate", "rates") and i > 0 and tokens[i - 1] in NOT_POLICY_RATE:
            continue
        if tok in SUBJECTS:
            near = tokens[max(0, i - WINDOW): i] + tokens[i + 1: i + 1 + WINDOW]
            direction = sum(DIRECTIONS.get(t, 0) for t in near)
            total += SUBJECTS[tok] * (1 if direction > 0 else -1 if direction < 0 else 0)
    return total


def label(sentence: str) -> str:
    score = sentence_score(sentence)
    return "hawkish" if score > 0 else "dovish" if score < 0 else "neutral"
