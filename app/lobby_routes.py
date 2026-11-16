"""HTTP and WebSocket routes for live multiplayer and player-vs-bot lobbies."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.lobby import LobbyError, LobbyManager
from app.models import User
from app.schemas import CreateLobbyRequest, LobbySummary
from app.security import get_valid_session

router = APIRouter(tags=["lobbies"])


def get_lobby_manager_http(request: Request) -> LobbyManager:
    """Retrieve the shared LobbyManager from FastAPI application state."""
    return request.app.state.lobby_manager


def _authenticate_websocket(websocket: WebSocket, manager: LobbyManager) -> User | None:
    settings: Settings = getattr(websocket.app.state, "settings", None) or get_settings()
    raw_token = websocket.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    with manager.session_factory() as db:
        session_row = get_valid_session(db, raw_token)
        if session_row is None:
            return None
        user = db.get(User, session_row.user_id)
        if user is None or user.is_bot:
            return None
        db.expunge(user)
        return user


@router.get(
    "/api/lobbies",
    response_model=list[LobbySummary],
    summary="List active and waiting game tables",
)
def list_lobbies(
    _current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[LobbyManager, Depends(get_lobby_manager_http)],
) -> list[LobbySummary]:
    return [LobbySummary(**item) for item in manager.list_tables()]


@router.post(
    "/api/lobbies",
    response_model=LobbySummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new player-vs-player or player-vs-bot table",
)
def create_lobby(
    payload: CreateLobbyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[LobbyManager, Depends(get_lobby_manager_http)],
) -> LobbySummary:
    try:
        table = manager.create_table(
            creator=current_user,
            game_type=payload.game_type,
            opponent_type=payload.opponent_type,
            bot_strategy=payload.bot_strategy,
            ante=payload.ante,
            min_bet=payload.min_bet,
            max_bet=payload.max_bet,
        )
    except LobbyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return LobbySummary(**manager.table_summary(table))


@router.get(
    "/api/lobbies/{table_id}",
    response_model=LobbySummary,
    summary="Get safe public metadata for a single table",
)
def get_lobby(
    table_id: int,
    _current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[LobbyManager, Depends(get_lobby_manager_http)],
) -> LobbySummary:
    table = manager.get_table(table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found.")
    return LobbySummary(**manager.table_summary(table))


@router.websocket("/ws/lobbies/{table_id}")
async def lobby_websocket(websocket: WebSocket, table_id: int) -> None:
    """Authenticate via session cookie and stream server-authoritative game events."""
    manager: LobbyManager = websocket.app.state.lobby_manager
    user = _authenticate_websocket(websocket, manager)
    if user is None:
        await websocket.close(code=4401)
        return

    table = manager.get_table(table_id)
    if table is None:
        await websocket.close(code=4404)
        return

    seat_idx = await manager.connect_player(table, user, websocket)
    if seat_idx is None:
        await websocket.close(code=4409)
        return

    try:
        while True:
            raw_text = await websocket.receive_text()
            await manager.handle_message(table, seat_idx, raw_text)
    except WebSocketDisconnect:
        await manager.disconnect_player(table, seat_idx)
