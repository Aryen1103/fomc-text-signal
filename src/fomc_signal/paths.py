"""Project paths. All data lives under ``data/`` (gitignored); outputs under ``results/``."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = DATA / "cache"
HTML_CACHE = CACHE / "html"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results"
