from fastapi import APIRouter, FastAPI

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    app = FastAPI(title="Niff")
    app.include_router(router)
    return app


app = create_app()
