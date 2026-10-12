"""CSV encoding and delimiter detection.

We try UTF-8 with and without BOM first, then fall back to ``charset-normalizer``
to pick the most likely encoding. Delimiter is detected by ``csv.Sniffer`` on
the first non-empty line, with a tiny manual fallback for the common
semicolon case.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from charset_normalizer import from_bytes


@dataclass
class Detection:
    encoding: str
    delimiter: str
    text: str  # full decoded content (decoded once, then sliced by callers)


def detect(raw: bytes) -> Detection:
    # Try strict UTF-8 (with or without BOM).
    try:
        text = raw.decode("utf-8-sig")
        delimiter = _guess_delimiter(text)
        return Detection(encoding="utf-8", delimiter=delimiter, text=text)
    except UnicodeDecodeError:
        pass

    # Fall back to charset-normalizer.
    best = from_bytes(raw).best()
    if best is None:
        # Last resort: latin-1 (never fails).
        text = raw.decode("latin-1")
        return Detection(encoding="latin-1", delimiter=_guess_delimiter(text), text=text)
    encoding = best.encoding
    text = str(best)
    return Detection(encoding=encoding, delimiter=_guess_delimiter(text), text=text)


def _guess_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:5])
    if not sample.strip():
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        # Heuristic: pick the most frequent candidate in the first 5 lines.
        candidates = [",", ";", "\t", "|"]
        first = sample.splitlines()[0]
        counts = {c: first.count(c) for c in candidates}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def preview(text: str, delimiter: str, n: int = 20) -> list[list[str]]:
    """Return the first ``n`` rows as a list of lists of strings."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    out: list[list[str]] = []
    for i, row in enumerate(reader):
        if i >= n:
            break
        out.append(row)
    return out


def all_rows(text: str, delimiter: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [r for r in reader]
