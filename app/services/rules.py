"""Auto-categorization rules.

A rule has a (case-insensitive substring) pattern and a target
category. Rules are evaluated in ascending ``position`` order, the
first match wins. Manual category assignments (``manual_category=True``
on a transaction) are sticky: rules must never overwrite them.

This module exposes:

* :func:`apply_to_description` — pure function for testing, returns
  the matching ``category_id`` or ``None``.
* :func:`apply_to_transaction` — used by the import commit and the
  re-apply endpoint. Only assigns a category when the transaction
  does not already have a manual one.
* :func:`reapply_uncategorized` — bulk re-apply, only touching rows
  whose category is None and that are not flagged as manual.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, select

from ..models.rule import Rule
from ..models.transaction import Transaction


def apply_to_description(description: str, rules: Iterable[Rule]) -> int | None:
    """Return the ``category_id`` of the first rule whose pattern is
    a (case-insensitive, whitespace-trimmed) substring of
    ``description``, or ``None`` if nothing matches.
    """
    if not description:
        return None
    needle = description.strip().lower()
    if not needle:
        return None
    for rule in sorted(rules, key=lambda r: (r.position, r.id or 0)):
        if not rule.pattern:
            continue
        haystack = rule.pattern.strip().lower()
        if haystack and haystack in needle:
            return rule.category_id
    return None


def load_user_rules(session: Session, user_id: int) -> list[Rule]:
    return list(
        session.exec(
            select(Rule)
            .where(Rule.user_id == user_id)
            .order_by(Rule.position.asc(), Rule.id.asc())
        ).all()
    )


def apply_to_transaction(
    session: Session, transaction: Transaction, rules: list[Rule] | None = None
) -> bool:
    """Assign a category to ``transaction`` if rules match and the
    existing assignment isn't sticky (manual). Returns True if the
    transaction's category changed.
    """
    if transaction.manual_category:
        return False
    if transaction.category_id is not None:
        # The row already has a category chosen by the user/system
        # (not flagged as manual) — leave it alone.
        return False
    if rules is None:
        rules = load_user_rules(session, transaction.user_id)
    cat_id = apply_to_description(transaction.description, rules)
    if cat_id is None:
        return False
    transaction.category_id = cat_id
    session.add(transaction)
    return True


def reapply_uncategorized(
    session: Session, user_id: int, rules: list[Rule] | None = None
) -> int:
    """Apply rules to every non-sticky, uncategorized transaction.
    Returns the number of rows whose category was changed.
    """
    if rules is None:
        rules = load_user_rules(session, user_id)
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.category_id.is_(None))  # type: ignore[union-attr]
        .where(Transaction.manual_category == False)  # noqa: E712
    )
    changed = 0
    for tx in session.exec(stmt).all():
        if apply_to_transaction(session, tx, rules):
            changed += 1
    if changed:
        session.commit()
    return changed
