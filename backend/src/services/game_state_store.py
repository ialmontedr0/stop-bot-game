import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete as sa_delete

from src.db.engine import async_session_factory
from src.db.models import GameStateCache

logger = logging.getLogger(__name__)

# ── Helpers de serialización ────────────────────────────────────────────────

LOBBY_SERIALIZABLE = {
    "game_id", "group_chat_id", "host_telegram_id", "host_name",
    "message_chat_id", "message_id", "player_telegram_ids",
    "player_display_names", "started",
}

ROUND_SERIALIZABLE = {
    "game_id", "group_chat_id", "round_number", "letter", "categories",
    "message_chat_id", "message_id", "host_telegram_id", "round_time",
    "include_n", "submitted_player_ids", "submission_order",
    "complete_player_ids", "first_completer_id", "first_completer_db_id",
    "first_completer_name", "leader_id", "stop_presses", "total_players",
    "total_rounds", "stop_message_chat_id", "stop_message_id",
    "letter_message_chat_id", "letter_message_id", "player_names",
    "inter_round_message_id", "cancelled", "validation_mode",
}


def _serialize_dict(d: dict[int, str]) -> dict[str, str]:
    return {str(k): v for k, v in d.items()}


def _deserialize_dict(d: dict[str, str]) -> dict[int, str]:
    return {int(k): v for k, v in d.items()}


def lobby_to_dict(state) -> dict[str, Any]:
    out = {}
    for k in LOBBY_SERIALIZABLE:
        if k == "player_names":
            continue
        out[k] = getattr(state, k)
    return out


def round_to_dict(state) -> dict[str, Any]:
    out = {}
    for k in ROUND_SERIALIZABLE:
        val = getattr(state, k)
        if k in ("submitted_player_ids", "complete_player_ids"):
            out[k] = list(val)
        elif k == "player_names":
            out[k] = _serialize_dict(val)
        else:
            out[k] = val
    return out


def dict_to_lobby(data: dict[str, Any]):
    from src.services.game_orchestrator import LobbyState

    data.pop("player_names", None)
    return LobbyState(
        game_id=data["game_id"],
        group_chat_id=data["group_chat_id"],
        host_telegram_id=data["host_telegram_id"],
        host_name=data["host_name"],
        message_chat_id=data["message_chat_id"],
        message_id=data["message_id"],
        player_telegram_ids=list(data["player_telegram_ids"]),
        player_display_names=list(data["player_display_names"]),
        started=data["started"],
    )


def dict_to_round(data: dict[str, Any]):
    from src.services.round_manager import RoundState

    player_names_raw = data.get("player_names", {})
    if player_names_raw and isinstance(next(iter(player_names_raw.keys())), str):
        player_names = _deserialize_dict(player_names_raw)
    else:
        player_names = player_names_raw

    return RoundState(
        game_id=data["game_id"],
        group_chat_id=data["group_chat_id"],
        round_number=data["round_number"],
        letter=data["letter"],
        categories=list(data["categories"]),
        message_chat_id=data["message_chat_id"],
        message_id=data["message_id"],
        host_telegram_id=data.get("host_telegram_id", 0),
        round_time=data.get("round_time", 60),
        include_n=data.get("include_n", False),
        submitted_player_ids=set(data.get("submitted_player_ids", [])),
        submission_order=list(data.get("submission_order", [])),
        complete_player_ids=set(data.get("complete_player_ids", [])),
        first_completer_id=data.get("first_completer_id"),
        first_completer_db_id=data.get("first_completer_db_id"),
        first_completer_name=data.get("first_completer_name"),
        leader_id=data.get("leader_id"),
        stop_presses=data.get("stop_presses", 0),
        total_players=data["total_players"],
        total_rounds=data.get("total_rounds", 5),
        stop_message_chat_id=data.get("stop_message_chat_id"),
        stop_message_id=data.get("stop_message_id"),
        letter_message_chat_id=data.get("letter_message_chat_id"),
        letter_message_id=data.get("letter_message_id"),
        player_names=player_names,
        inter_round_message_id=data.get("inter_round_message_id"),
        cancelled=data.get("cancelled", False),
        validation_mode=data.get("validation_mode", "local"),
    )


# ── Key helpers ─────────────────────────────────────────────────────────────

_LOBBY_PREFIX = "lobby:"
_ROUND_PREFIX = "round:"
_LETTER_PREFIX = "letter_pending:"
_RBG_PREFIX = "rounds_by_group:"


def _key_lobby(group_chat_id: int) -> str:
    return f"{_LOBBY_PREFIX}{group_chat_id}"


def _key_round(game_id: int) -> str:
    return f"{_ROUND_PREFIX}{game_id}"


def _key_letter_pending(game_id: int) -> str:
    return f"{_LETTER_PREFIX}{game_id}"


def _key_rbg(group_chat_id: int) -> str:
    return f"{_RBG_PREFIX}{group_chat_id}"


# ── GameStateStore ABC ──────────────────────────────────────────────────────


class GameStateStore(ABC):
    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        ...

    @abstractmethod
    async def get(self, key: str) -> str | None:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...

    @abstractmethod
    async def keys(self, prefix: str = "") -> list[str]:
        ...

    @abstractmethod
    async def get_all(self, prefix: str = "") -> dict[str, str]:
        ...

    @abstractmethod
    async def clear_all(self) -> None:
        ...

    # ── Domain methods ──────────────────────────────────────────────────────

    async def set_lobby(self, state) -> None:
        data = lobby_to_dict(state)
        await self.set(_key_lobby(state.group_chat_id), json.dumps(data))

    async def get_lobby(self, group_chat_id: int):
        raw = await self.get(_key_lobby(group_chat_id))
        if raw is None:
            return None
        return dict_to_lobby(json.loads(raw))

    async def delete_lobby(self, group_chat_id: int) -> None:
        await self.delete(_key_lobby(group_chat_id))

    async def get_all_lobbies(self) -> dict[int, Any]:
        raw = await self.get_all(_LOBBY_PREFIX)
        result: dict[int, Any] = {}
        for key, val in raw.items():
            gcid = int(key[len(_LOBBY_PREFIX):])
            result[gcid] = dict_to_lobby(json.loads(val))
        return result

    async def set_round(self, state) -> None:
        data = round_to_dict(state)
        await self.set(_key_round(state.game_id), json.dumps(data))

    async def get_round(self, game_id: int):
        raw = await self.get(_key_round(game_id))
        if raw is None:
            return None
        return dict_to_round(json.loads(raw))

    async def delete_round(self, game_id: int) -> None:
        await self.delete(_key_round(game_id))

    async def get_all_rounds(self) -> dict[int, Any]:
        raw = await self.get_all(_ROUND_PREFIX)
        result: dict[int, Any] = {}
        for key, val in raw.items():
            gid = int(key[len(_ROUND_PREFIX):])
            result[gid] = dict_to_round(json.loads(val))
        return result

    async def set_letter_pending(self, state) -> None:
        data = round_to_dict(state)
        await self.set(_key_letter_pending(state.game_id), json.dumps(data))

    async def get_letter_pending(self, game_id: int):
        raw = await self.get(_key_letter_pending(game_id))
        if raw is None:
            return None
        return dict_to_round(json.loads(raw))

    async def delete_letter_pending(self, game_id: int) -> None:
        await self.delete(_key_letter_pending(game_id))

    async def get_all_letter_pending(self) -> dict[int, Any]:
        raw = await self.get_all(_LETTER_PREFIX)
        result: dict[int, Any] = {}
        for key, val in raw.items():
            gid = int(key[len(_LETTER_PREFIX):])
            result[gid] = dict_to_round(json.loads(val))
        return result

    async def set_rounds_by_group(self, group_chat_id: int, game_id: int) -> None:
        await self.set(_key_rbg(group_chat_id), str(game_id))

    async def get_rounds_by_group(self, group_chat_id: int) -> int | None:
        raw = await self.get(_key_rbg(group_chat_id))
        if raw is None:
            return None
        return int(raw)

    async def delete_rounds_by_group(self, group_chat_id: int) -> None:
        await self.delete(_key_rbg(group_chat_id))

    async def get_all_rounds_by_group(self) -> dict[int, int]:
        raw = await self.get_all(_RBG_PREFIX)
        result: dict[int, int] = {}
        for key, val in raw.items():
            gcid = int(key[len(_RBG_PREFIX):])
            result[gcid] = int(val)
        return result


# ── RedisGameStateStore ─────────────────────────────────────────────────────


class RedisGameStateStore(GameStateStore):
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def set(self, key: str, value: str) -> None:
        await self._redis.set(key, value)

    async def get(self, key: str) -> str | None:
        val = await self._redis.get(key)
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def keys(self, prefix: str = "") -> list[str]:
        result = await self._redis.keys(f"{prefix}*")
        return [k.decode("utf-8") if isinstance(k, bytes) else k for k in result]

    async def get_all(self, prefix: str = "") -> dict[str, str]:
        raw_keys = await self.keys(prefix)
        if not raw_keys:
            return {}
        values = await self._redis.mget(*raw_keys)
        out: dict[str, str] = {}
        for k, v in zip(raw_keys, values, strict=False):
            if v is not None:
                decoded = v.decode("utf-8") if isinstance(v, bytes) else v
                out[k] = decoded
        return out

    async def clear_all(self) -> None:
        all_keys = await self.keys()
        if all_keys:
            await self._redis.delete(*all_keys)


# ── PgGameStateStore ────────────────────────────────────────────────────────


class PgGameStateStore(GameStateStore):
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or async_session_factory

    async def set(self, key: str, value: str) -> None:
        async with self._session_factory() as session:
            existing = await session.get(GameStateCache, key)
            if existing:
                existing.value = value
            else:
                session.add(GameStateCache(key=key, value=value))
            await session.commit()

    async def get(self, key: str) -> str | None:
        async with self._session_factory() as session:
            row = await session.get(GameStateCache, key)
            return row.value if row else None

    async def delete(self, key: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(GameStateCache, key)
            if row:
                await session.delete(row)
                await session.commit()

    async def keys(self, prefix: str = "") -> list[str]:
        async with self._session_factory() as session:
            stmt = select(GameStateCache.key).where(
                GameStateCache.key.like(f"{prefix}%")
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def get_all(self, prefix: str = "") -> dict[str, str]:
        async with self._session_factory() as session:
            stmt = select(GameStateCache).where(
                GameStateCache.key.like(f"{prefix}%")
            )
            result = await session.execute(stmt)
            return {row.key: row.value for row in result.scalars().all()}

    async def clear_all(self) -> None:
        async with self._session_factory() as session:
            await session.execute(sa_delete(GameStateCache))
            await session.commit()


# ── Factory ─────────────────────────────────────────────────────────────────


async def create_game_state_store(redis_client=None) -> GameStateStore:
    if redis_client is not None:
        try:
            await redis_client.ping()
            logger.info("Usando RedisGameStateStore (Redis disponible)")
            return RedisGameStateStore(redis_client)
        except Exception:
            logger.warning("Redis no disponible, usando PgGameStateStore (PostgreSQL)")

    logger.info("Usando PgGameStateStore (PostgreSQL)")
    return PgGameStateStore()
