"""Export endpoints: CSV and XLSX download."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response

from ..routers.deps import CurrentUser, SessionDep
from ..services import exports as exports_service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/transactions.csv")
def export_transactions_csv(user: CurrentUser, session: SessionDep):
    body = exports_service.export_csv(session, user.id)
    today = datetime.utcnow().strftime("%Y%m%d")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=pocketledger-{today}.csv"},
    )


@router.get("/transactions.xlsx")
def export_transactions_xlsx(user: CurrentUser, session: SessionDep):
    body = exports_service.export_xlsx(session, user.id)
    today = datetime.utcnow().strftime("%Y%m%d")
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=pocketledger-{today}.xlsx"
        },
    )
