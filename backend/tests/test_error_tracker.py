import asyncio
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.db.models import ErrorLog
from src.services.error_tracker import ErrorTracker, _get_solution, KNOWN_SOLUTIONS


# Get the actual module object (not shadowed by instance in __init__.py)
_et_module = sys.modules['src.services.error_tracker']


class TestGetSolution:
    def test_exact_match(self):
        sol, severity = _get_solution("sqlalchemy.exc.OperationalError")
        assert "PostgreSQL" in sol
        assert severity == "CRITICAL"

    def test_substring_match(self):
        sol, severity = _get_solution("sqlalchemy.exc.CustomError")
        assert sol is not None
        assert sol == KNOWN_SOLUTIONS["Exception"][0]

    def test_unknown_exception(self):
        sol, severity = _get_solution("foo.bar.BazError")
        assert sol == KNOWN_SOLUTIONS["Exception"][0]
        assert severity == "MEDIUM"

    def test_aiogram_bad_request(self):
        sol, severity = _get_solution("aiogram.exceptions.TelegramBadRequest")
        assert "Telegram rechazó" in sol
        assert severity == "LOW"

    def test_redis_connection_error(self):
        sol, severity = _get_solution("redis.exceptions.ConnectionError")
        assert "Redis" in sol
        assert severity == "CRITICAL"


class TestErrorTrackerCapture:
    @pytest.mark.asyncio
    async def test_capture_exception_success(self):
        with patch.object(_et_module, 'async_session_factory') as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()

            async def fake_refresh(log):
                log.id = 1

            mock_session.commit = AsyncMock()
            mock_session.refresh = fake_refresh
            mock_session_factory.return_value.__aenter__.return_value = mock_session

            tracker = ErrorTracker()
            exc = ValueError("algo salió mal")

            log_id = await tracker.capture_exception(
                exc=exc,
                handler="test_handler",
                user_id=1,
                game_id=42,
                telegram_id=123456789,
                context={"foo": "bar"},
            )

            assert log_id is not None
            assert tracker.captured_count == 1
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_db_failure_does_not_crash(self):
        with patch.object(_et_module, 'async_session_factory') as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock(side_effect=Exception("DB fail"))
            mock_session_factory.return_value.__aenter__.return_value = mock_session

            tracker = ErrorTracker()
            exc = RuntimeError("test error")

            log_id = await tracker.capture_exception(exc=exc)
            assert log_id is None
            assert tracker.captured_count == 0

    def test_captured_count(self):
        tracker = ErrorTracker()
        assert tracker.captured_count == 0


class TestErrorTrackerTrackErrors:
    @pytest.mark.asyncio
    async def test_decorator_passthrough_on_success(self):
        tracker = ErrorTracker()

        @tracker.track_errors(handler_name="test")
        async def success_func():
            return 42

        result = await success_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorator_captures_and_raises(self):
        tracker = ErrorTracker()
        tracker.capture_exception = AsyncMock(return_value=1)

        @tracker.track_errors(handler_name="test")
        async def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_func()

        tracker.capture_exception.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_decorator_passes_cancelled(self):
        tracker = ErrorTracker()
        tracker.capture_exception = AsyncMock(return_value=1)

        @tracker.track_errors(handler_name="test")
        async def cancelled_func():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancelled_func()

        tracker.capture_exception.assert_not_called()


class TestErrorTrackerGenerateReport:
    @pytest.mark.asyncio
    async def test_report_format_when_no_errors(self):
        with patch.object(_et_module, 'async_session_factory') as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session

            mock_repo = AsyncMock()
            mock_repo.get_total_count = AsyncMock(return_value=0)
            mock_repo.count_unresolved = AsyncMock(return_value=0)
            mock_repo.get_most_frequent_exception = AsyncMock(return_value=[])
            mock_repo.get_recent = AsyncMock(return_value=[])

            with patch.object(_et_module, 'ErrorLogRepository', return_value=mock_repo):
                tracker = ErrorTracker()
                report = await tracker.generate_report()
                assert "DIAGNÓSTICO" in report


class TestErrorLogModel:
    def test_error_log_creation(self):
        log = ErrorLog(
            level="ERROR",
            handler="test",
            exception_type="ValueError",
            exception_message="test message",
            resolved=False,
        )
        assert log.level == "ERROR"
        assert log.exception_type == "ValueError"
        assert log.resolved is False
        assert "ErrorLog" in repr(log)
