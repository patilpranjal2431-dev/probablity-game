"""FastAPI application entry point for Edge Lab."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_optional_user
from app.auth import router as auth_router
from app.calibration_routes import router as calibration_router
from app.config import Settings, get_settings
from app.database import SessionLocal, get_db, init_db
from app.game_routes import router as game_router
from app.leaderboard_routes import router as leaderboard_router
from app.lobby import LobbyManager
from app.lobby_routes import router as lobby_router
from app.models import User
from app.orderbook_routes import router as orderbook_router
from app.quant_routes import router as quant_router
from app.schemas import HealthResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
PUBLIC_ASSETS_DIR = Path(__file__).resolve().parent.parent / "public" / "assets"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Ensure database tables exist when the application boots."""
    init_db()
    yield


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or SessionLocal

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Virtual-coin quantitative finance game platform.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.lobby_manager = LobbyManager(
        resolved_session_factory,
        turn_timeout_seconds=resolved_settings.turn_timeout_seconds,
    )
    application.include_router(auth_router)
    application.include_router(quant_router)
    application.include_router(game_router)
    application.include_router(lobby_router)
    application.include_router(leaderboard_router)
    application.include_router(calibration_router)
    application.include_router(orderbook_router)

    if STATIC_DIR.is_dir():
        application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if PUBLIC_ASSETS_DIR.is_dir():
        application.mount("/assets", StaticFiles(directory=str(PUBLIC_ASSETS_DIR)), name="assets")

    @application.get("/", include_in_schema=False)
    def home_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/profile", include_in_schema=False, response_model=None)
    def profile_page(
        current_user: Annotated[User | None, Depends(get_optional_user)],
    ) -> FileResponse | RedirectResponse:
        if current_user is None:
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return FileResponse(STATIC_DIR / "profile.html")

    @application.get("/lobby", include_in_schema=False, response_model=None)
    def lobby_page(
        current_user: Annotated[User | None, Depends(get_optional_user)],
    ) -> FileResponse | RedirectResponse:
        if current_user is None:
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return FileResponse(STATIC_DIR / "lobby.html")

    @application.get("/lab", include_in_schema=False)
    def lab_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "lab.html")

    @application.get("/arena", include_in_schema=False)
    def arena_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "arena.html")

    @application.get("/leaderboard", include_in_schema=False)
    def leaderboard_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "leaderboard.html")

    @application.get("/skill-vs-luck", include_in_schema=False)
    def skill_vs_luck_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "skill_vs_luck.html")

    @application.get("/docs", include_in_schema=False)
    @application.get("/algorithms", include_in_schema=False)
    def docs_page() -> FileResponse:
        return FileResponse(DOCS_DIR / "index.html")

    @application.get("/bankroll", include_in_schema=False)
    def bankroll_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "bankroll.html")

    @application.get("/calibration", include_in_schema=False, response_model=None)
    def calibration_page(
        current_user: Annotated[User | None, Depends(get_optional_user)],
    ) -> FileResponse | RedirectResponse:
        if current_user is None:
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return FileResponse(STATIC_DIR / "calibration.html")

    @application.get("/orderbook", include_in_schema=False, response_model=None)
    def orderbook_page(
        current_user: Annotated[User | None, Depends(get_optional_user)],
    ) -> FileResponse | RedirectResponse:
        if current_user is None:
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return FileResponse(STATIC_DIR / "orderbook.html")

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Check service and database health",
    )
    def health_check(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connectivity check failed.",
            ) from exc

        return HealthResponse(
            status="ok",
            app=resolved_settings.app_name,
            version=resolved_settings.app_version,
            database="ok",
        )

    return application


app = create_app()
