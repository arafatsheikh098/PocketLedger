"""Dedup key generation per F4.

The duplicate detection key is::

    sha256(account_id | iso_date | amount_minor | normalized_description | occurrence_index)

where:

* ``account_id`` is the SQL id of the account the row is being imported into.
* ``iso_date`` is the date in YYYY-MM-DD form.
* ``amount_minor`` is the signed integer minor-units value.
* ``normalized_description`` is the lowercased description with all
  whitespace collapsed to a single space and stripped.
* ``occurrence_index`` is a per-batch counter so that two genuinely
  identical same-day transactions are both kept: first one gets index 0,
  second one gets index 1.

This is the same recipe the spec calls out in F4 ("occurrence index")
to defeat the "two same-day purchases collapse" failure mode.
"""
from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def normalize_description(description: str) -> str:
    return _WS_RE.sub(" ", description).strip().lower()


def make_dedup_key(
    *, account_id: int, iso_date: str, amount_minor: int, description: str, occurrence_index: int
) -> str:
    norm = normalize_description(description)
    payload = f"{account_id}|{iso_date}|{amount_minor}|{norm}|{occurrence_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
