import pytest

from src.db.repositories.error_log_repository import ErrorLogRepository


class TestErrorLogRepository:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, async_session):
        repo = ErrorLogRepository(async_session)
        log = await repo.create(
            level="ERROR",
            handler="test_handler",
            user_id=1,
            exception_type="ValueError",
            exception_message="algo salió mal",
            context={"extra": "data"},
        )
        assert log.id is not None
        assert log.level == "ERROR"
        assert log.handler == "test_handler"

    @pytest.mark.asyncio
    async def test_get_unresolved(self, async_session):
        repo = ErrorLogRepository(async_session)
        await repo.create(level="ERROR", handler="h1")
        await repo.create(level="ERROR", handler="h2")
        all_logs = await repo.get_unresolved()
        assert len(all_logs) >= 2

    @pytest.mark.asyncio
    async def test_count_by_level(self, async_session):
        repo = ErrorLogRepository(async_session)
        await repo.create(level="ERROR", handler="h1")
        await repo.create(level="WARNING", handler="h2")
        counts = await repo.count_by_level()
        assert counts.get("ERROR", 0) >= 1
        assert counts.get("WARNING", 0) >= 1
