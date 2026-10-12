"""CSV import wizard routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.scoped import scoped_get, scoped_query
from ..models.account import Account
from ..models.import_batch import ImportBatch
from ..models.transaction import Transaction
from ..routers.deps import CurrentUser, SessionDep, is_demo, require_csrf
from ..services import csv_detect, import_batch, mapping

router = APIRouter(prefix="/imports", tags=["imports"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_imports(request: Request, user: CurrentUser, session: SessionDep):
    batches = session.exec(
        scoped_query(session, user.id, ImportBatch).order_by(ImportBatch.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "imports/list.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "batches": batches,
        },
    )


@router.get("/new", response_model=None)
def new_form(request: Request, user: CurrentUser, session: SessionDep):
    accounts = session.exec(scoped_query(session, user.id, Account)).all()
    if not accounts:
        return RedirectResponse("/accounts?error=Create+an+account+first", status_code=303)
    return templates.TemplateResponse(
        request,
        "imports/upload.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "accounts": accounts,
            "error": None,
        },
    )


@router.post("/upload", response_model=None)
def upload(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    account_id: int = Form(...),
    file: UploadFile = File(...),
):
    if scoped_get(session, user.id, Account, account_id) is None:
        return _upload_error("invalid account")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return _upload_error("only .csv files are accepted")
    raw = file.file.read()
    if len(raw) > 5 * 1024 * 1024:
        return _upload_error("file too large")
    # Store the bytes in a server-side session key (we reuse the import
    # session id). The simplest approach: stash on the request and re-detect
    # in the next step. We re-parse here too.
    try:
        det = csv_detect.detect(raw)
        preview = csv_detect.preview(det.text, det.delimiter, 20)
    except Exception as exc:
        return _upload_error(f"could not parse file: {exc}")
    # Save the raw file in a temp file for the next step.
    import os
    import tempfile

    os.makedirs("/tmp/pocketledger-imports", exist_ok=True)
    tmp_path = os.path.join(
        tempfile.mkdtemp(prefix="pl-imp-", dir="/tmp/pocketledger-imports"), file.filename
    )
    with open(tmp_path, "wb") as f:
        f.write(raw)
    return templates.TemplateResponse(
        request,
        "imports/mapping.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "accounts": [scoped_get(session, user.id, Account, account_id)],
            "account_id": account_id,
            "tmp_path": tmp_path,
            "filename": file.filename,
            "detection": {"encoding": det.encoding, "delimiter": det.delimiter},
            "preview": preview,
            "date_formats": list(mapping.DATE_FORMATS),
            "error": None,
        },
    )


def _upload_error(msg: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(f"/imports/new?error={quote(msg)}", status_code=303)


@router.post("/dry-run", response_model=None)
def dry_run(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    account_id: int = Form(...),
    tmp_path: str = Form(...),
    date_col: int = Form(...),
    description_col: int = Form(...),
    amount_mode: str = Form("signed"),
    amount_col: Annotated[int | None, Form()] = None,
    debit_col: Annotated[int | None, Form()] = None,
    credit_col: Annotated[int | None, Form()] = None,
    date_format: str = Form(...),
    decimal_sep: str = Form("."),
    thousands_sep: str = Form(","),
    expenses_are_positive: Annotated[str | None, Form()] = None,
):
    import os

    if not os.path.exists(tmp_path):
        raise HTTPException(400, "upload session expired; please re-upload")
    with open(tmp_path, "rb") as f:
        raw = f.read()
    m = mapping.Mapping(
        date_col=date_col,
        description_col=description_col,
        amount_mode=amount_mode,
        amount_col=amount_col,
        debit_col=debit_col,
        credit_col=credit_col,
        date_format=date_format,
        decimal_sep=decimal_sep,
        thousands_sep=thousands_sep,
        expenses_are_positive=expenses_are_positive == "on",
    )
    result = import_batch.dry_run(
        session=session, user_id=user.id, account_id=account_id, raw_bytes=raw, m=m
    )
    return templates.TemplateResponse(
        request,
        "imports/dry_run.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "account_id": account_id,
            "tmp_path": tmp_path,
            "mapping_json": m.to_json(),
            "result": result,
        },
    )


@router.post("/commit", response_model=None)
def commit(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    account_id: int = Form(...),
    tmp_path: str = Form(...),
    mapping_json: str = Form(...),
    filename: str = Form(...),
):
    import os

    if not os.path.exists(tmp_path):
        raise HTTPException(400, "upload session expired; please re-upload")
    with open(tmp_path, "rb") as f:
        raw = f.read()
    m = mapping.Mapping.from_json(mapping_json)
    try:
        batch, errors = import_batch.commit(
            session=session,
            user_id=user.id,
            account_id=account_id,
            filename=filename,
            raw_bytes=raw,
            m=m,
            skip_errors=True,
        )
    except mapping.RowError as exc:
        return RedirectResponse(f"/imports?error={str(exc)}", status_code=303)
    return RedirectResponse(f"/imports/{batch.id}", status_code=303)


@router.get("/{batch_id}", response_model=None)
def batch_detail(
    batch_id: int,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
):
    batch = scoped_get(session, user.id, ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404)
    rows = session.exec(
        scoped_query(session, user.id, Transaction).where(Transaction.import_batch_id == batch_id)
    ).all()
    return templates.TemplateResponse(
        request,
        "imports/batch.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "batch": batch,
            "rows": rows,
        },
    )


@router.post("/{batch_id}/undo", response_model=None)
def undo(
    batch_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
):
    n = import_batch.undo(session, user.id, batch_id)
    return RedirectResponse(f"/imports?undone={n}", status_code=303)
