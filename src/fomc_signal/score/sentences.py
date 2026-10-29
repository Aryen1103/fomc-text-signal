"""Split cleaned FOMC text into sentences, the unit every tone scorer labels."""

from __future__ import annotations

import re

# Abbreviations that end in a period without ending a sentence.
_ABBREVIATIONS = ["U.S.", "a.m.", "p.m.", "Mr.", "Ms.", "Mrs.", "Dr.", "No.", "e.g.", "i.e.",
                  "St.", "Inc.", "Co.", "Jr.", "vs.", "etc.", "approx."]
_PLACEHOLDER = "⁣"  # invisible separator, never in the source text
_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[\"'(\[]?[A-Z0-9])")
MIN_WORDS = 3  # "Inflation remains elevated." is 3 words; shorter fragments carry no tone


def split_sentences(text: str) -> list[str]:
    """Sentences in reading order, paragraph by paragraph."""
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        p = re.sub(r"\s+", " ", paragraph).strip()
        if not p:
            continue
        for abbr in _ABBREVIATIONS:
            p = p.replace(abbr, abbr.replace(".", _PLACEHOLDER))
        for s in _SPLIT.split(p):
            s = s.replace(_PLACEHOLDER, ".").strip()
            if len(s.split()) >= MIN_WORDS:
                out.append(s)
    return out
