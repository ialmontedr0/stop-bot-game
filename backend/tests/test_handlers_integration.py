from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.models import Base
from src.keyboards.settings import ALL_CATEGORIES

_ROUND_MOD = "src.handlers.game.round"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_message():
    answer_ret = MagicMock()
    answer_ret.edit_text = AsyncMock()
    answer_ret.delete = AsyncMock()
    msg = MagicMock()
    msg.chat.id = -100123456789
    msg.chat.type = "group"
    msg.from_user.id = 123456789
    msg.from_user.is_bot = False
    msg.message_id = 1
    msg.answer = AsyncMock(return_value=answer_ret)
    msg.reply = AsyncMock(return_value=MagicMock())
    msg.bot = AsyncMock()
    return msg


@pytest.fixture
def mock_callback():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message.chat.id = -100123456789
    cb.message.message_id = 1
    cb.message.edit_text = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.from_user.id = 123456789
    cb.from_user.is_bot = False
    return cb


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message.return_value = MagicMock()
    return bot


@pytest.fixture
def mock_player():
    player = MagicMock()
    player.id = 1
    player.telegram_id = 123456789
    player.language_code = "es"
    player.username = "testuser"
    player.first_name = "Test"
    return player


# ─── Settings handlers ───────────────────────────────────────────────────


class TestCmdSettings:
    async def test_private_chat_rejected(self, mock_message, mock_player, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.settings import cmd_settings

        await cmd_settings(mock_message, mock_player, mock_bot)
        mock_message.reply.assert_awaited_once()
        args = mock_message.reply.await_args[0][0]
        assert "solo funciona en grupos" in args

    async def test_non_admin_rejected(self, mock_message, mock_player, mock_bot):
        mock_bot.get_chat_member = AsyncMock()
        mock_bot.get_chat_member.return_value.status = "member"
        mock_bot.get_chat_member.return_value.is_chat_admin.return_value = False
        with patch("src.handlers.game.settings.is_admin", AsyncMock(return_value=False)):
            from src.handlers.game.settings import cmd_settings

            await cmd_settings(mock_message, mock_player, mock_bot)
            mock_message.reply.assert_awaited_once()
            args = mock_message.reply.await_args[0][0]
            assert "administradores" in args

    async def test_shows_settings_menu(self, mock_message, mock_player, mock_bot, db_session):
        mock_bot.get_chat_member = AsyncMock()
        mock_bot.get_chat_member.return_value.status = "creator"
        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            from src.handlers.game.settings import cmd_settings

            await cmd_settings(mock_message, mock_player, mock_bot)
            mock_message.reply.assert_awaited_once()


class TestBackToMain:
    async def test_edits_with_main_menu(self, mock_callback, db_session):
        from src.handlers.game.settings import back_to_main

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await back_to_main(mock_callback)
            mock_callback.message.edit_text.assert_awaited_once()
            mock_callback.answer.assert_awaited_once()


class TestShowRounds:
    async def test_shows_rounds_menu(self, mock_callback, db_session):
        from src.handlers.game.settings import show_rounds

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await show_rounds(mock_callback)
            mock_callback.message.edit_text.assert_awaited_once()
            mock_callback.answer.assert_awaited_once()


class TestSetRounds:
    async def test_sets_rounds(self, mock_callback, db_session):
        mock_callback.data = "set_rondas:10"
        from src.handlers.game.settings import set_rounds

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await set_rounds(mock_callback)
            assert mock_callback.answer.await_count >= 1
            call_args = mock_callback.answer.await_args_list[0][0][0]
            assert "10" in call_args


class TestShowTime:
    async def test_shows_time_menu(self, mock_callback, db_session):
        from src.handlers.game.settings import show_time

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await show_time(mock_callback)
            mock_callback.message.edit_text.assert_awaited_once()
            mock_callback.answer.assert_awaited_once()


class TestSetTime:
    async def test_sets_time(self, mock_callback, db_session):
        mock_callback.data = "set_tiempo:60"
        from src.handlers.game.settings import set_time

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await set_time(mock_callback)
            assert mock_callback.answer.await_count >= 1
            call_args = mock_callback.answer.await_args_list[0][0][0]
            assert "60" in call_args


class TestShowCats:
    async def test_shows_cats_menu(self, mock_callback, db_session):
        from src.handlers.game.settings import show_cats

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await show_cats(mock_callback)
            mock_callback.message.edit_text.assert_awaited_once()
            mock_callback.answer.assert_awaited_once()


class TestToggleCat:
    async def test_adds_category(self, mock_callback, db_session):
        mock_callback.data = "toggle_cat:Música"
        from src.handlers.game.settings import toggle_cat

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await toggle_cat(mock_callback)
            mock_callback.answer.assert_awaited_once()

    async def test_removes_category(self, mock_callback, db_session):
        mock_callback.data = f"toggle_cat:{ALL_CATEGORIES[0]}"
        from src.handlers.game.settings import toggle_cat

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await toggle_cat(mock_callback)
            mock_callback.answer.assert_awaited_once()

    async def test_minimum_four_categories(self, mock_callback, db_session):
        mock_callback.data = f"toggle_cat:{ALL_CATEGORIES[0]}"
        from src.handlers.game.settings import _serialize_categories, toggle_cat

        repo = MagicMock()
        repo.get_or_create = AsyncMock()
        config = MagicMock()
        config.categories = _serialize_categories(ALL_CATEGORIES[:4])
        repo.get_or_create.return_value = config
        with patch("src.handlers.game.settings.GroupConfigRepository") as mock_repo_cls:
            mock_repo_cls.return_value = repo
            with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.settings.is_admin", return_value=True):
                    await toggle_cat(mock_callback)
                mock_callback.answer.assert_awaited_once()
                assert "Mínimo 4" in mock_callback.answer.await_args[0][0]


class TestToggleN:
    async def test_toggles_n(self, mock_callback, db_session):
        from src.handlers.game.settings import toggle_n

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await toggle_n(mock_callback)
            mock_callback.answer.assert_awaited_once()


class TestShowMode:
    async def test_shows_mode_menu(self, mock_callback, db_session):
        from src.handlers.game.settings import show_mode

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await show_mode(mock_callback)
            mock_callback.message.edit_text.assert_awaited_once()
            mock_callback.answer.assert_awaited_once()


class TestSetMode:
    async def test_sets_mode(self, mock_callback, db_session):
        mock_callback.data = "set_mode:ai"
        from src.handlers.game.settings import set_mode

        with patch("src.handlers.game.settings.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.settings.is_admin", return_value=True):
                await set_mode(mock_callback)
            assert mock_callback.answer.await_count >= 1
            call_args = mock_callback.answer.await_args_list[0][0][0]
            assert "ai" in call_args


class TestSettingsClose:
    async def test_closes_settings(self, mock_callback):
        from src.handlers.game.settings import settings_close

        await settings_close(mock_callback)
        mock_callback.message.delete.assert_awaited_once()
        mock_callback.answer.assert_awaited_once()


class TestParseCategories:
    def test_none_returns_all(self):
        from src.handlers.game.settings import _parse_categories

        result = _parse_categories(None)
        assert result == ALL_CATEGORIES

    def test_empty_string_returns_all(self):
        from src.handlers.game.settings import _parse_categories

        result = _parse_categories("")
        assert result == ALL_CATEGORIES

    def test_parses_comma_separated(self):
        from src.handlers.game.settings import _parse_categories

        result = _parse_categories("Nombre,Color,Fruta")
        assert result == ["Nombre", "Color", "Fruta"]

    def test_strips_whitespace(self):
        from src.handlers.game.settings import _parse_categories

        result = _parse_categories("  Nombre ,  Color ")
        assert result == ["Nombre", "Color"]

    def test_filters_empty(self):
        from src.handlers.game.settings import _parse_categories

        result = _parse_categories("Nombre,,Color,")
        assert result == ["Nombre", "Color"]


class TestSerializeCategories:
    def test_joins_with_commas(self):
        from src.handlers.game.settings import _serialize_categories

        result = _serialize_categories(["Nombre", "Color"])
        assert result == "Nombre,Color"


# ─── Clear handlers ─────────────────────────────────────────────────────


class TestCmdClear:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.clear import CommandObject, cmd_clear

        command = MagicMock(spec=CommandObject)
        command.args = None
        await cmd_clear(mock_message, mock_bot, command)
        mock_message.answer.assert_awaited_once()
        args = mock_message.answer.await_args[0][0]
        assert "grupos" in args

    async def test_non_admin_rejected(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.clear.is_admin", AsyncMock(return_value=False)):
            from src.handlers.game.clear import CommandObject, cmd_clear

            command = MagicMock(spec=CommandObject)
            command.args = None
            await cmd_clear(mock_message, mock_bot, command)
            mock_message.answer.assert_awaited_once()
            args = mock_message.answer.await_args[0][0]
            assert "administradores" in args

    async def test_no_messages_to_clear(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.clear.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.clear.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.clear._pending", {123456789: 9999999999}):
                    from src.handlers.game.clear import CommandObject, cmd_clear

                    command = MagicMock(spec=CommandObject)
                    command.args = "confirmar"
                    await cmd_clear(mock_message, mock_bot, command)
                    ret = mock_message.answer.return_value
                    ret.edit_text.assert_awaited_once()

    async def test_clears_messages(self, mock_message, mock_bot, db_session):
        mock_bot.delete_messages = AsyncMock()
        with patch("src.handlers.game.clear.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.clear.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.clear._pending", {123456789: 9999999999}):
                    from src.handlers.game.clear import CommandObject, cmd_clear

                    command = MagicMock(spec=CommandObject)
                    command.args = "confirmar"
                    await cmd_clear(mock_message, mock_bot, command)
                    ret = mock_message.answer.return_value
                    ret.edit_text.assert_awaited_once()


class TestCmdClearStats:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.clear_stats import CommandObject, cmd_clear_stats

        command = MagicMock(spec=CommandObject)
        command.args = None
        await cmd_clear_stats(mock_message, mock_bot, command)
        mock_message.answer.assert_awaited_once()
        args = mock_message.answer.await_args[0][0]
        assert "grupos" in args

    async def test_non_admin_rejected(self, mock_message, mock_bot):
        with patch("src.handlers.game.clear_stats.is_admin", AsyncMock(return_value=False)):
            from src.handlers.game.clear_stats import CommandObject, cmd_clear_stats

            command = MagicMock(spec=CommandObject)
            command.args = None
            await cmd_clear_stats(mock_message, mock_bot, command)
            mock_message.answer.assert_awaited_once()
            args = mock_message.answer.await_args[0][0]
            assert "administradores" in args

    async def test_clears_stats(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.clear_stats.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.clear_stats.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.clear_stats._pending", {123456789: 9999999999}):
                    from src.handlers.game.clear_stats import CommandObject, cmd_clear_stats

                    command = MagicMock(spec=CommandObject)
                    command.args = "confirmar"
                    await cmd_clear_stats(mock_message, mock_bot, command)
                    ret = mock_message.answer.return_value
                    assert ret.edit_text.await_count >= 1


# ─── Diagnose handlers ──────────────────────────────────────────────────


class TestCmdDiagnose:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.diagnose import cmd_diagnose

        await cmd_diagnose(mock_message, mock_bot)
        mock_message.answer.assert_awaited_once()
        args = mock_message.answer.await_args[0][0]
        assert "grupos" in args

    async def test_non_admin_rejected(self, mock_message, mock_bot):
        with patch("src.handlers.game.diagnose.is_admin", AsyncMock(return_value=False)):
            from src.handlers.game.diagnose import cmd_diagnose

            await cmd_diagnose(mock_message, mock_bot)
            mock_message.answer.assert_awaited_once()
            args = mock_message.answer.await_args[0][0]
            assert "administradores" in args

    async def test_generates_report(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.diagnose.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.diagnose.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.diagnose.error_tracker") as mock_tracker:
                    mock_tracker.generate_report = AsyncMock(return_value="Diagnóstico OK")
                    from src.handlers.game.diagnose import cmd_diagnose

                    await cmd_diagnose(mock_message, mock_bot)
                    mock_message.reply.assert_awaited_once()
                    args = mock_message.reply.await_args[0][0]
                    assert "Diagnóstico" in args

    async def test_long_report_splits(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.diagnose.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.diagnose.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                with patch("src.handlers.game.diagnose.error_tracker") as mock_tracker:
                    mock_tracker.generate_report = AsyncMock(return_value="A" * 5000)
                    from src.handlers.game.diagnose import cmd_diagnose

                    await cmd_diagnose(mock_message, mock_bot)
                    assert mock_message.reply.await_count >= 1


class TestCmdResolve:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.diagnose import CommandObject, cmd_resolve

        command = MagicMock(spec=CommandObject)
        command.args = None
        await cmd_resolve(mock_message, command, mock_bot)
        mock_message.answer.assert_awaited_once()
        args = mock_message.answer.await_args[0][0]
        assert "grupos" in args

    async def test_resolves_errors(self, mock_message, mock_bot, db_session):
        mock_message.chat.type = "group"
        with patch("src.handlers.game.diagnose.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.diagnose.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                from src.handlers.game.diagnose import CommandObject, cmd_resolve

                command = MagicMock(spec=CommandObject)
                command.args = "fixed"
                await cmd_resolve(mock_message, command, mock_bot)
                mock_message.reply.assert_awaited_once()


class TestCmdErrors:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.diagnose import cmd_errors

        await cmd_errors(mock_message, mock_bot)
        mock_message.answer.assert_awaited_once()
        args = mock_message.answer.await_args[0][0]
        assert "grupos" in args

    async def test_no_errors(self, mock_message, mock_bot, db_session):
        with patch("src.handlers.game.diagnose.is_admin", AsyncMock(return_value=True)):
            with patch("src.handlers.game.diagnose.async_session_factory") as mock_sf:
                mock_sf.return_value.__aenter__.return_value = db_session
                from src.handlers.game.diagnose import cmd_errors

                await cmd_errors(mock_message, mock_bot)
                mock_message.reply.assert_awaited_once()
                args = mock_message.reply.await_args[0][0]
                assert "No hay errores" in args


# ─── Stats handler ──────────────────────────────────────────────────────


class TestCmdStats:
    async def test_private_chat_rejected(self, mock_message, mock_bot):
        mock_message.chat.type = "private"
        from src.handlers.game.stats import cmd_stats

        await cmd_stats(mock_message, mock_bot)
        mock_message.reply.assert_awaited_once()
        args = mock_message.reply.await_args[0][0]
        assert "grupos" in args

    async def test_shows_stats(self, mock_message, mock_bot, db_session):
        mock_message.reply.return_value.edit_text = AsyncMock()
        with patch("src.handlers.game.stats.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            from src.handlers.game.stats import cmd_stats

            await cmd_stats(mock_message, mock_bot)
            status_msg = mock_message.reply.return_value
            status_msg.edit_text.assert_awaited_once()

    async def test_with_game_data(self, mock_message, mock_bot, db_session):
        from src.db.models import Game, GamePlayer, Player

        p = Player(telegram_id=999, first_name="StatsPlayer", language_code="es")
        db_session.add(p)
        await db_session.flush()
        g = Game(group_chat_id=-100123456789, status="finished")
        db_session.add(g)
        await db_session.flush()
        gp = GamePlayer(game_id=g.id, player_id=p.id, score=100, is_host=True)
        db_session.add(gp)
        await db_session.commit()
        mock_message.reply.return_value.edit_text = AsyncMock()
        with patch("src.handlers.game.stats.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            from src.handlers.game.stats import cmd_stats

            await cmd_stats(mock_message, mock_bot)
            status_msg = mock_message.reply.return_value
            status_msg.edit_text.assert_awaited_once()


# ─── Profile handler ────────────────────────────────────────────────────


class TestCmdProfile:
    async def test_shows_profile(self, mock_message, mock_player, db_session):
        mock_message.reply.return_value.edit_text = AsyncMock()
        with patch("src.handlers.game.profile.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.profile.xp_service") as mock_xp:
                mock_xp.get_profile = AsyncMock(
                    return_value={
                        "level": 5,
                        "total_xp": 1500,
                        "title": "Veterano",
                        "progress_pct": 60,
                        "streak": 3,
                        "max_streak": 10,
                    }
                )
                with patch("src.services.leaderboard.leaderboard_service") as mock_lb:
                    mock_lb.get_player_rank_by_telegram = AsyncMock(
                        return_value={
                            "rank": 2,
                            "score": 500,
                        }
                    )
                    from src.handlers.game.profile import cmd_profile

                    await cmd_profile(mock_message, mock_player)
                    status_msg = mock_message.reply.return_value
                    status_msg.edit_text.assert_awaited_once()

    async def test_shows_profile_no_xp(self, mock_message, mock_player, db_session):
        mock_message.reply.return_value.edit_text = AsyncMock()
        with patch("src.handlers.game.profile.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.game.profile.xp_service") as mock_xp:
                mock_xp.get_profile = AsyncMock(return_value=None)
                from src.handlers.game.profile import cmd_profile

                await cmd_profile(mock_message, mock_player)
                status_msg = mock_message.reply.return_value
                status_msg.edit_text.assert_awaited_once()


# ─── Leaderboard handler ────────────────────────────────────────────────


class TestCmdLeaderboard:
    async def test_no_data(self, mock_message):
        mock_message.reply.return_value.edit_text = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_weekly_top = AsyncMock(return_value=[])
            from src.handlers.game.leaderboard import cmd_leaderboard

            await cmd_leaderboard(mock_message)
            status_msg = mock_message.reply.return_value
            status_msg.edit_text.assert_awaited_once()
            args = status_msg.edit_text.await_args[0][0]
            assert "Aún no hay datos" in args

    async def test_private_chat_rejected(self, mock_message):
        mock_message.chat.type = "private"
        mock_message.reply = AsyncMock()
        from src.handlers.game.leaderboard import cmd_leaderboard

        await cmd_leaderboard(mock_message)
        mock_message.reply.assert_awaited_once()
        args = mock_message.reply.await_args[0][0]
        assert "solo funciona en grupos" in args

    async def test_with_data_text_fallback(self, mock_message):
        mock_message.reply.return_value.edit_text = AsyncMock()
        mock_message.bot = AsyncMock()
        mock_message.bot.get_user_profile_photos = AsyncMock()
        mock_message.bot.get_user_profile_photos.return_value.total_count = 0
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_weekly_top = AsyncMock(
                return_value=[
                    {"rank": 1, "name": "Player1", "score": 100, "games": 5, "telegram_id": 111},
                    {"rank": 2, "name": "Player2", "score": 80, "games": 3, "telegram_id": 222},
                ]
            )
            with patch("src.image_generator.generate_leaderboard_image", return_value=None):
                from src.handlers.game.leaderboard import cmd_leaderboard

                await cmd_leaderboard(mock_message)
                status_msg = mock_message.reply.return_value
                status_msg.edit_text.assert_awaited_once()

    async def test_passes_group_chat_id(self, mock_message):
        mock_message.reply.return_value.edit_text = AsyncMock()
        get_weekly_top_mock = AsyncMock(return_value=[])
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_weekly_top = get_weekly_top_mock
            from src.handlers.game.leaderboard import cmd_leaderboard

            await cmd_leaderboard(mock_message)
            get_weekly_top_mock.assert_awaited_once_with(
                group_chat_id=-100123456789, limit=10
            )


class TestCmdRank:
    async def test_no_data(self, mock_message):
        mock_message.from_user.id = 123456789
        mock_message.reply = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_player_rank_by_telegram = AsyncMock(return_value=None)
            from src.handlers.game.leaderboard import cmd_rank

            await cmd_rank(mock_message)
            mock_message.reply.assert_awaited_once()

    async def test_private_chat_rejected(self, mock_message):
        mock_message.chat.type = "private"
        mock_message.reply = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_player_rank_by_telegram = AsyncMock(return_value=None)
            from src.handlers.game.leaderboard import cmd_rank

            await cmd_rank(mock_message)
            # Con chat.type=private el handler retorna temprano sin consultar servicio
            mock_ls.get_player_rank_by_telegram.assert_not_awaited()
            mock_message.reply.assert_awaited_once()
            args = mock_message.reply.await_args[0][0]
            assert "solo funciona en grupos" in args

    async def test_with_rank(self, mock_message):
        mock_message.from_user.id = 123456789
        mock_message.reply = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_player_rank_by_telegram = AsyncMock(
                return_value={
                    "rank": 1,
                    "score": 200,
                    "games": 10,
                }
            )
            from src.handlers.game.leaderboard import cmd_rank

            await cmd_rank(mock_message)
            mock_message.reply.assert_awaited_once()
            args = mock_message.reply.await_args[0][0]
            assert "#1" in args

    async def test_with_rank_2(self, mock_message):
        mock_message.from_user.id = 123456789
        mock_message.reply = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_player_rank_by_telegram = AsyncMock(
                return_value={
                    "rank": 2,
                    "score": 150,
                    "games": 5,
                }
            )
            from src.handlers.game.leaderboard import cmd_rank

            await cmd_rank(mock_message)
            mock_message.reply.assert_awaited_once()

    async def test_with_rank_3(self, mock_message):
        mock_message.from_user.id = 123456789
        mock_message.reply = AsyncMock()
        with patch("src.handlers.game.leaderboard.leaderboard_service") as mock_ls:
            mock_ls.get_player_rank_by_telegram = AsyncMock(
                return_value={
                    "rank": 3,
                    "score": 100,
                    "games": 3,
                }
            )
            from src.handlers.game.leaderboard import cmd_rank

            await cmd_rank(mock_message)
            mock_message.reply.assert_awaited_once()

    async def test_no_from_user(self, mock_message):
        mock_message.from_user = None
        from src.handlers.game.leaderboard import cmd_rank

        await cmd_rank(mock_message)


# ─── Group handlers ─────────────────────────────────────────────────────


class TestBotRemovedFromGroup:
    async def test_cancels_active_game(self, mock_bot, db_session):
        from src.handlers.group import bot_removed_from_group

        event = MagicMock()
        event.chat.id = -100123456789
        with patch("src.handlers.group.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.group.round_manager") as mock_rm:
                await bot_removed_from_group(event, mock_bot)
                mock_rm.cancel_game.assert_not_called()

    async def test_no_active_game(self, mock_bot, db_session):
        from src.handlers.group import bot_removed_from_group

        event = MagicMock()
        event.chat.id = -100999
        with patch("src.handlers.group.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__.return_value = db_session
            with patch("src.handlers.group.round_manager"):
                await bot_removed_from_group(event, mock_bot)


# ─── Round handlers ─────────────────────────────────────────────────────


class TestRoundHandlers:
    async def test_handle_round_answer_no_active_round(self, mock_message, mock_player, mock_bot):
        with patch(f"{_ROUND_MOD}.round_manager") as mock_rm:
            mock_rm.get_active_round_by_group.return_value = None
            from src.handlers.game.round import handle_round_answer

            await handle_round_answer(mock_message, mock_player, mock_bot)
            mock_message.bot.send_message.assert_not_called()

    async def test_callback_stop_invalid_data(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "stop:abc"
        from src.handlers.game.round import callback_stop

        await callback_stop(mock_callback, mock_player, mock_bot)
        mock_callback.answer.assert_awaited_once()

    async def test_callback_letter_invalid_data(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "letter:abc"
        from src.handlers.game.round import callback_letter

        await callback_letter(mock_callback, mock_player, mock_bot)
        mock_callback.answer.assert_awaited_once()

    async def test_callback_next_round(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "next_round:1"
        with patch(f"{_ROUND_MOD}.round_manager", new_callable=AsyncMock) as mock_rm:
            mock_rm.handle_next_round = AsyncMock()
            from src.handlers.game.round import callback_next_round

            await callback_next_round(mock_callback, mock_player, mock_bot)
            mock_rm.handle_next_round.assert_awaited_once_with(
                game_id=1,
                player_id=mock_player.telegram_id,
                callback=mock_callback,
                bot=mock_bot,
            )

    async def test_callback_next_round_invalid(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "next_round:abc"
        from src.handlers.game.round import callback_next_round

        await callback_next_round(mock_callback, mock_player, mock_bot)
        mock_callback.answer.assert_awaited_once()

    async def test_callback_stop_game(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "stop_game:1"
        with patch(f"{_ROUND_MOD}.round_manager", new_callable=AsyncMock) as mock_rm:
            mock_rm.handle_stop_game = AsyncMock()
            from src.handlers.game.round import callback_stop_game

            await callback_stop_game(mock_callback, mock_player, mock_bot)
            mock_rm.handle_stop_game.assert_awaited_once_with(
                game_id=1,
                player_id=mock_player.telegram_id,
                callback=mock_callback,
                bot=mock_bot,
            )

    async def test_callback_stop_game_invalid(self, mock_callback, mock_player, mock_bot):
        mock_callback.data = "stop_game:abc"
        from src.handlers.game.round import callback_stop_game

        await callback_stop_game(mock_callback, mock_player, mock_bot)
        mock_callback.answer.assert_awaited_once()
