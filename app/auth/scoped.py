"""Helpers to enforce per-user scoping on every query.

The point of this module is to make it impossible to forget to filter
by ``user_id``: every read and every write goes through one of these
helpers, and tests assert isolation by trying to read another user's
rows through the public helpers.
"""
from __future__ import annotations

from typing import Any, TypeVar

from sqlmodel import Session, SQLModel, select

T = TypeVar("T", bound=SQLModel)


def user_owned(model: type[T]) -> type[T]:
    """Marker: returns the model class unchanged. Used only for typing.

    Real scoping happens in :func:`scoped_query` and
    :func:`scoped_get`. The marker is here so that ``from app.auth.scoped
    import user_owned`` reads as intent at every call site.
    """
    return model


def scoped_query(session: Session, user_id: int, model: type[T]) -> Any:
    """Build a SELECT filtered to a single user.

    Every router calls this. The function name includes the word
    'scoped' so a code review can grep for it.
    """
    return select(model).where(model.user_id == user_id)  # type: ignore[attr-defined]


def scoped_get(session: Session, user_id: int, model: type[T], obj_id: int) -> T | None:
    """Fetch a single object by id, but only if it belongs to the user.

    Returns None if the row does not exist OR if it belongs to a
    different user. Callers must treat None as 'not found or not yours'.
    """
    return session.exec(
        select(model).where(model.user_id == user_id).where(model.id == obj_id)  # type: ignore[attr-defined]
    ).first()
