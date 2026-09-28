"""Boilerplate removal for statements and minutes, plus sentence splitting.

Cleaning works on paragraphs. Every removed paragraph (or sentence) is returned
with the name of the rule that removed it, so the stripped text can be audited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------
# shared rules

VOTING = re.compile(
    r"^(Voting|Votes?\s+(for|against)|Absent and not voting)\b",
    re.IGNORECASE,
)
DISSENT_ONLY = re.compile(r"^[A-Z][\w.'\- ]{2,60}\s(dissented|voted against)\b")
MEDIA = re.compile(r"(For media inquiries|Media [Ii]nquiries|Media Contacts?:|202-452-\d{4})")
DISCOUNT_APPROVAL_SENT = re.compile(r"requests?\s+submitted by the Boards? of Directors", re.IGNORECASE)

# statement pages
STATEMENT_START = re.compile(r"^(For (immediate )?release\b|For use at\b)", re.IGNORECASE)
STATEMENT_FOOTER = re.compile(
    r"^(\d{4} Monetary policy|Last [Uu]pdate|Home\b|\[?Return to top|Back to Top"
    r"|Implementation Note|Related Information|Board of Governors of the Federal Reserve System$)",
)
LINK_LINE = re.compile(r"^(Share|PDF|HTML|Attachment.*|Press Conference|Projection Materials)$")

# minutes
MINUTES_END = re.compile(r"^It was agreed that the next meeting")
MINUTES_PROCEDURAL = re.compile(
    r"^(By unanimous vote|The agenda for this meeting|Secretary'?s note|The elected members"
    r"|A (joint )?meeting of the Federal Open Market Committee (and the Board of Governors .*?)?was held"
    r"|Present:|Attended\b|Return to (text|top)|Footnotes?$|\d+\.\s+Attended)",
    re.IGNORECASE,
)
# where the substantive discussion of a meeting begins (first match wins)
MINUTES_START = re.compile(
    r"^(Developments in Financial Markets"
    r"|The (SOMA |System Open Market Account |Deputy )?[Mm]anager (of the System Open Market Account )?"
    r"(\(SOMA\) |for Foreign Operations )?(also |first )?(reported|discussed|noted|summarized|reviewed|turned)"
    r"|The information reviewed (at|for) (this|the \w+) meeting"
    r"|Staff Review of the Economic Situation"
    r"|The information (received|available) (since|at the time of) the"
    r")"
)
# organisational/legal/attendance text that precedes the substantive discussion; only
# applied to paragraphs before the start anchor (special-topic discussions there are kept)
MINUTES_ORGANISATIONAL = re.compile(
    r"(authoriz|[Dd]irective|Procedural Instructions|Program for Security|Rules? (of|Regarding)"
    r"|advices? of the election|\belected\b|officers of the Committee|selected to serve"
    r"|Manager shall|pursuant to|swap|foreign currenc|reaffirm|amend|ratif|attended"
    r"|Division of|Governors;|notation vote|Federal Reserve Bank of [A-Z][\w. ]+;"
    r"|paragraph|Selected Bank|Permitted Foreign Securities|Eligible Securities|System balances"
    r"|Subcommittee|foreign monetary authorities|Chair(man)? shall|service fee|continuing rules"
    r"|instruments in question|Federal agency issues|foreign central banks|United States Treasury"
    r"|such operation|disorderly market conditions|accounts at foreign|:$)"
)
ENUMERATED = re.compile(r"^\(?([a-z]|[ivx]+|[A-Z]|\d{1,2})[.)]\s")
# The annually re-adopted "Statement on Longer-Run Goals and Monetary Policy Strategy" is
# reproduced in January minutes; its paragraphs are boilerplate and removed everywhere.
LONGER_RUN_GOALS = re.compile(
    r"^(The Federal Open Market Committee \(FOMC\) is firmly committed"
    r"|Inflation, employment, and long-term interest rates fluctuate"
    r"|The inflation rate over the longer run is (primarily )?determined"
    r"|The maximum level of employment is"
    r"|Monetary policy actions tend to influence economic activity"
    r"|In setting monetary policy, the Committee seeks"
    r"|The Committee's policy decisions reflect its longer-run goals"
    r"|The Committee intends to review these principles"
    r"|The Committee's employment and inflation objectives are generally complementary"
    r"|The Committee judges that longer-term inflation expectations that are well anchored"
    r"|The Committee sets forth its principles regarding)"
)
NAVIGATION = re.compile(r"^(skip to|Menu$|Search$|Home\s*\|)", re.IGNORECASE)
OPEN_QUOTES = ("“", '"', "‘‘", "``")
CLOSE_QUOTES = ("”", '"', "''")


_NAME_LIST_LOWER_OK = {"and", "of", "the", "van", "der", "de", "la"}


def _is_name_list(p: str) -> bool:
    """True for the name lists that follow "Voting for this action:" (or "None.")."""
    words = re.findall(r"[A-Za-z][\w'\-]*", p)
    return bool(words) and all(w[0].isupper() or w in _NAME_LIST_LOWER_OK for w in words)


def _capitalised_share(p: str) -> float:
    words = re.findall(r"[A-Za-z][\w'\-]*", p)
    return sum(w[0].isupper() for w in words) / max(len(words), 1)


@dataclass
class CleanResult:
    """Kept paragraphs and a log of removed text with the rule that removed it."""

    kept: list[str]
    stripped: list[tuple[str, str]] = field(default_factory=list)  # (rule, text)

    @property
    def text(self) -> str:
        """Kept paragraphs joined by blank lines."""
        return "\n\n".join(self.kept)


def _strip_sentences(para: str, pattern: re.Pattern, rule: str, log: list) -> str:
    kept = []
    for s in split_sentences(para):
        if pattern.search(s):
            log.append((rule, s))
        else:
            kept.append(s)
    return " ".join(kept)


def clean_statement(paragraphs: list[str]) -> CleanResult:
    """Remove header, footer, voting lists, media contacts and procedural sentences."""
    log: list[tuple[str, str]] = []
    start = next((i for i, p in enumerate(paragraphs) if STATEMENT_START.search(p)), None)
    if start is None:
        body = list(paragraphs)
    else:
        log += [("header", p) for p in paragraphs[: start + 1]]
        body = paragraphs[start + 1:]
    end = next((i for i, p in enumerate(body) if STATEMENT_FOOTER.search(p)), len(body))
    log += [("footer", p) for p in body[end:]]
    body = body[:end]

    kept = []
    for p in body:
        if VOTING.search(p) or DISSENT_ONLY.search(p):
            log.append(("voting", p))
        elif MEDIA.search(p):
            log.append(("media_contact", p))
        elif LINK_LINE.search(p) or len(p.split()) < 5:
            log.append(("fragment", p))
        else:
            p = _strip_sentences(p, DISCOUNT_APPROVAL_SENT, "discount_approval", log)
            if p:
                kept.append(p)
    return CleanResult(kept, log)


def clean_minutes(paragraphs: list[str]) -> CleanResult:
    """Keep the substantive discussion of a minutes document.

    The substantive discussion normally starts with the markets report (``MINUTES_START``).
    Paragraphs before that anchor are kept only if they are not attendance lists,
    organisational/legal text (authorizations, elections, rules) or enumerated legal
    clauses, so special-topic discussions placed before the markets report survive.
    Everything from "It was agreed that the next meeting..." on is dropped (adjournment,
    notation votes, signature, footnotes). Throughout: quoted statement/directive text,
    voting blocks, procedural paragraphs and short fragments are removed.
    """
    log: list[tuple[str, str]] = []
    start = next((i for i, p in enumerate(paragraphs) if MINUTES_START.search(p)), None)
    if start is None:
        start = 0
        log.append(("warning", "no start anchor found"))
    end = next((i for i, p in enumerate(paragraphs) if i >= start and MINUTES_END.search(p)),
               len(paragraphs))
    log += [("tail", p) for p in paragraphs[end:]]

    kept: list[str] = []
    in_quote = False
    in_vote = False
    for i, p in enumerate(paragraphs[:end]):
        opens = p.startswith(OPEN_QUOTES)
        if in_quote or opens:
            log.append(("quoted_statement_or_directive", p))
            # a quoted block ends on a paragraph that ends with a closing quote
            in_quote = not p.rstrip().endswith(CLOSE_QUOTES)
            continue
        if VOTING.search(p):
            log.append(("voting", p))
            in_vote = True
            continue
        if in_vote and _is_name_list(p):
            log.append(("voting", p))  # the list of names following a "Voting for" line
            continue
        in_vote = False
        if i < start and (_capitalised_share(p) > 0.35 or p.rstrip().endswith((";", ","))):
            log.append(("header_attendance", p))
        elif i < start and (MINUTES_ORGANISATIONAL.search(p) or ENUMERATED.search(p)
                            or p[:1].islower()):  # lower-case start: a broken legal clause
            log.append(("header_organisational", p))
        elif LONGER_RUN_GOALS.search(p):
            log.append(("longer_run_goals_statement", p))
        elif NAVIGATION.search(p):
            log.append(("navigation", p))
        elif MINUTES_PROCEDURAL.search(p):
            log.append(("procedural", p))
        elif MEDIA.search(p):
            log.append(("media_contact", p))
        elif len(p.split()) < 8:
            log.append(("fragment", p))
        elif len(p.split()) < 15 and not p.rstrip().endswith((".", ":", "?", "”", '"')):
            log.append(("heading", p))
        else:
            kept.append(p)
    return CleanResult(kept, log)


# --------------------------------------------------------------------------------
# sentence splitting

_ABBREV = [
    "Mr", "Mrs", "Ms", "Messrs", "Mses", "Dr", "St", "Jr", "Sr", "No", "Nos", "vs",
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec",
    "Inc", "Corp", "Co", "e.g", "i.e", "a.m", "p.m", "U.S", "U.K", "etc", "approx", "Gov",
]
_ABBREV_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in _ABBREV) + r")\.", re.IGNORECASE)
_SENT_END = re.compile(
    r"(?:(?<=[.!?])|(?<=[.!?][\"”’')\]]))\s+(?=[\"“(\[]?[A-Z0-9])"
)
_PLACEHOLDER = "\u0000"


def split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Rule based: splits after ``.``, ``!`` or ``?`` (plus closing quotes/brackets) followed
    by whitespace and an upper-case letter or digit, except after common abbreviations
    (Mr., U.S., St. Louis, a.m., p.m., month abbreviations) and single-letter initials.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    protected = _ABBREV_RE.sub(lambda m: m.group(0)[:-1] + _PLACEHOLDER, text)
    # initials such as "Janet L. Yellen" or "J. Alfred Broaddus"
    protected = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", lambda m: m.group(1) + _PLACEHOLDER, protected)
    parts = _SENT_END.split(protected)
    return [p.replace(_PLACEHOLDER, ".").strip() for p in parts if p.strip()]
