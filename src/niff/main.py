import sqlite3
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from niff.config import Settings
from niff.db import connect, open_database
from niff.scheduler import start_scheduler
from niff.snapshot import build_snapshot

router = APIRouter()


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """One short-lived connection per request; SQLite connections aren't shared across threads."""
    settings: Settings = request.app.state.settings
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


class AccountOut(BaseModel):
    id: str
    plan_id: str
    name: str
    type: str
    on_budget: bool
    balance: int  # milliunits


class PlanOut(BaseModel):
    id: str
    name: str
    last_synced_at: datetime | None
    total: int  # milliunits


class SnapshotOut(BaseModel):
    net_worth: int  # milliunits
    plans: list[PlanOut]
    accounts: list[AccountOut]


@router.get("/snapshot")
def snapshot(conn: Conn, request: Request) -> SnapshotOut:
    """Net worth, per-plan totals and open accounts, all in milliunits."""
    settings: Settings = request.app.state.settings
    result = build_snapshot(conn, settings.ynab_plan_ids)
    return SnapshotOut(
        net_worth=result.net_worth,
        plans=[
            PlanOut(id=p.id, name=p.name, last_synced_at=p.last_synced_at, total=p.total)
            for p in result.plans
        ],
        accounts=[
            AccountOut(
                id=a.ynab_account_id,
                plan_id=a.plan_id,
                name=a.name,
                type=a.type,
                on_budget=a.on_budget,
                balance=a.balance,
            )
            for a in result.accounts
        ],
    )


@router.get("/healthz")
def healthz(conn: Conn) -> JSONResponse:
    try:
        conn.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        return JSONResponse({"status": "error"}, status_code=503)
    return JSONResponse({"status": "ok"})


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        open_database(resolved.db_path).close()
        scheduler = start_scheduler(resolved)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown()

    app = FastAPI(title="Niff", lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(router)
    return app


app = create_app()
