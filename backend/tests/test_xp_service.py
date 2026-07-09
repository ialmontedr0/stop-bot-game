import pytest
from src.services.xp_service import XPService, _calculate_level, _get_xp_for_next_level


class TestCalculateLevel:
    def test_level_1_at_zero_xp(self):
        assert _calculate_level(0) == 1

    def test_level_1_below_threshold(self):
        assert _calculate_level(50) == 1

    def test_level_2_at_exact_threshold(self):
        assert _calculate_level(100) == 2

    def test_level_5_at_exact_threshold(self):
        assert _calculate_level(800) == 5

    def test_level_10_at_exact_threshold(self):
        assert _calculate_level(4000) == 10

    def test_level_20_max(self):
        assert _calculate_level(99999) == 20

    def test_between_levels(self):
        assert _calculate_level(600) == 4


class TestGetXpForNextLevel:
    def test_level_1_needs_100(self):
        assert _get_xp_for_next_level(1) == 100

    def test_level_5_needs_1200(self):
        assert _get_xp_for_next_level(5) == 1200

    def test_level_20_returns_fallback(self):
        assert _get_xp_for_next_level(20) == 999999


class TestUpdateStreak:
    @pytest.mark.asyncio
    async def test_first_play_sets_streak_1(self):
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        mod = sys.modules["src.services.xp_service"]
        mock_session = AsyncMock()

        # First call in _get_or_create_streak: returns None
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result1)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        def refresh_side(obj):
            obj.current_streak = 0
            obj.max_streak = 0
            obj.last_played_date = None
        mock_session.refresh = AsyncMock(side_effect=refresh_side)

        # Second call outside _get_or_create for commit
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None

        with patch.object(mod, "async_session_factory") as m:
            m.return_value.__aenter__.return_value = mock_session

            result = await XPService.update_streak(1)
            assert result["current_streak"] == 1
            assert result["max_streak"] == 1

    @pytest.mark.asyncio
    async def test_consecutive_day_increments(self):
        from datetime import date, timedelta
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        real_date = date.today()
        yesterday = real_date - timedelta(days=1)

        streak_mock = MagicMock()
        streak_mock.current_streak = 1
        streak_mock.max_streak = 1
        streak_mock.last_played_date = yesterday

        mod = sys.modules["src.services.xp_service"]
        with patch.object(mod, "async_session_factory") as m:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = streak_mock
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()
            m.return_value.__aenter__.return_value = mock_session

            result = await XPService.update_streak(1)
            assert result["current_streak"] == 2
            assert result["max_streak"] == 2
            assert streak_mock.last_played_date == real_date

    @pytest.mark.asyncio
    async def test_missed_day_resets(self):
        from datetime import date, timedelta
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        two_days_ago = date.today() - timedelta(days=2)

        streak_mock = MagicMock()
        streak_mock.current_streak = 5
        streak_mock.max_streak = 5
        streak_mock.last_played_date = two_days_ago

        mod = sys.modules["src.services.xp_service"]
        with patch.object(mod, "async_session_factory") as m:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = streak_mock
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()
            m.return_value.__aenter__.return_value = mock_session

            result = await XPService.update_streak(1)
            assert result["current_streak"] == 1
            assert result["max_streak"] == 5


class TestAwardGameXp:
    @pytest.fixture(autouse=True)
    def mock_db(self):
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        xp_mod = sys.modules["src.services.xp_service"]

        self._patches = []
        p1 = patch.object(xp_mod, "async_session_factory")
        m = p1.start()
        self._patches.append(p1)

        import src.services.event_service as es_mod
        p_event = patch.object(
            es_mod.event_service, "get_active_multiplier", AsyncMock(return_value=1.0)
        )
        p_event.start()
        self._patches.append(p_event)

        mock_session = AsyncMock()

        # First call from _get_or_create_streak
        streak_result = MagicMock()
        streak_result.scalar_one_or_none.return_value = None
        # Second call from award_game_xp main
        xp_result = MagicMock()
        xp_result.scalar_one_or_none.return_value = None

        def execute_side(*args, **kwargs):
            from unittest.mock import MagicMock
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        mock_session.execute = AsyncMock(side_effect=execute_side)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        def refresh_side(obj):
            if hasattr(obj, 'player_id'):
                obj.current_streak = 0
                obj.max_streak = 0
                obj.last_played_date = None
                obj.xp = 0
                obj.level = 1
                obj.total_xp_earned = 0

        mock_session.refresh = AsyncMock(side_effect=refresh_side)
        m.return_value.__aenter__.return_value = mock_session
        self._mock_session = mock_session
        yield
        for p in self._patches:
            p.stop()

    @pytest.mark.asyncio
    async def test_award_basic_xp(self):
        result = await XPService.award_game_xp(1, final_position=2)
        assert result["xp_gained"] == 50
        assert result["level"] == 1
        assert result["leveled_up"] is False

    @pytest.mark.asyncio
    async def test_winner_gets_bonus(self):
        result = await XPService.award_game_xp(1, final_position=1)
        assert result["xp_gained"] == 150
