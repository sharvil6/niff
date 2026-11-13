import sqlite3
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from niff.config import Settings
from niff.db import connect, migrate

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
        resolved.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(resolved.db_path)
        try:
            migrate(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Niff", lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(router)
    return app


app = create_app()
