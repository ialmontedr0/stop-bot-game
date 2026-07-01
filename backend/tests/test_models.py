import pytest
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Answer,
    Game,
    GamePlayer,
    GroupConfig,
    Player,
    Round,
    WeeklyLeaderboard,
)


def test_player_construction():
    p = Player(telegram_id=1, first_name="A")
    assert p.telegram_id == 1
    assert p.first_name == "A"
    assert p.username is None
    assert p.last_name is None
    assert p.language_code is None
    assert p.game_players == []
    assert p.answers == []
    assert p.weekly_leaderboards == []


def test_game_construction():
    g = Game(group_chat_id=-1000)
    assert g.group_chat_id == -1000


def test_gameplayer_construction():
    gp = GamePlayer(game_id=1, player_id=1)
    assert gp.game_id == 1
    assert gp.player_id == 1


def test_gameplayer_host_flag():
    gp = GamePlayer(game_id=1, player_id=1, is_host=True)
    assert gp.is_host is True


def test_round_construction():
    r = Round(game_id=1, round_number=1, letter="A")
    assert r.letter == "A"
    assert r.round_number == 1


def test_answer_construction():
    a = Answer(round_id=1, player_id=1, game_player_id=1, word_slot="animal", raw_text="Perro")
    assert a.word_slot == "animal"
    assert a.raw_text == "Perro"
    assert a.is_correct is None
    assert a.normalized_text is None


def test_weekly_leaderboard_construction():
    wl = WeeklyLeaderboard(player_id=1, week_start=date(2026, 6, 29))
    assert wl.week_start == date(2026, 6, 29)


def test_group_config_construction():
    gc = GroupConfig(group_chat_id=-1000)
    assert gc.group_chat_id == -1000


@pytest.mark.asyncio
async def test_player_defaults_after_commit(async_session: AsyncSession):
    p = Player(telegram_id=2, first_name="B")
    async_session.add(p)
    await async_session.commit()
    await async_session.refresh(p)
    assert isinstance(p.created_at, datetime)


@pytest.mark.asyncio
async def test_game_defaults_after_commit(async_session: AsyncSession):
    g = Game(group_chat_id=-1001)
    async_session.add(g)
    await async_session.commit()
    await async_session.refresh(g)
    assert g.status == "lobby"
    assert g.current_round == 0
    assert g.total_rounds == 5
    assert g.finished_at is None


@pytest.mark.asyncio
async def test_gameplayer_defaults_after_commit(async_session: AsyncSession):
    gp = GamePlayer(game_id=1, player_id=1)
    async_session.add(gp)
    await async_session.commit()
    await async_session.refresh(gp)
    assert gp.score == 0
    assert isinstance(gp.joined_at, datetime)


@pytest.mark.asyncio
async def test_round_defaults_after_commit(async_session: AsyncSession):
    r = Round(game_id=1, round_number=1, letter="C")
    async_session.add(r)
    await async_session.commit()
    await async_session.refresh(r)
    assert r.status == "waiting"
    assert r.started_at is None
    assert r.stopped_at is None
    assert r.stopped_by_player_id is None


@pytest.mark.asyncio
async def test_answer_defaults_after_commit(async_session: AsyncSession):
    a = Answer(round_id=1, player_id=1, game_player_id=1, word_slot="x", raw_text="y")
    async_session.add(a)
    await async_session.commit()
    await async_session.refresh(a)
    assert a.score == 0
    assert isinstance(a.created_at, datetime)


@pytest.mark.asyncio
async def test_weekly_leaderboard_defaults_after_commit(async_session: AsyncSession):
    wl = WeeklyLeaderboard(player_id=1, week_start=date(2026, 6, 29))
    async_session.add(wl)
    await async_session.commit()
    await async_session.refresh(wl)
    assert wl.total_score == 0
    assert wl.games_played == 0
    assert wl.rank is None


@pytest.mark.asyncio
async def test_group_config_defaults_after_commit(async_session: AsyncSession):
    gc = GroupConfig(group_chat_id=-1002)
    async_session.add(gc)
    await async_session.commit()
    await async_session.refresh(gc)
    assert gc.default_rounds == 5
    assert gc.round_time == 60
    assert gc.categories is None
    assert gc.include_n is False
    assert gc.language == "es"


def test_game_status_transitions():
    g = Game(group_chat_id=-1, status="playing")
    assert g.status == "playing"
    g.status = "finished"
    assert g.status == "finished"


def test_player_weekly_leaderboards_relationship():
    p = Player(telegram_id=1, first_name="A")
    wl = WeeklyLeaderboard(player_id=1, week_start=date(2026, 6, 29))
    p.weekly_leaderboards.append(wl)
    assert len(p.weekly_leaderboards) == 1
    assert p.weekly_leaderboards[0] is wl


def test_player_answers_relationship():
    p = Player(telegram_id=1, first_name="A")
    a = Answer(round_id=1, player_id=1, game_player_id=1, word_slot="x", raw_text="y")
    p.answers.append(a)
    assert len(p.answers) == 1


def test_game_players_relationship():
    g = Game(group_chat_id=-1)
    gp = GamePlayer(game_id=1, player_id=1)
    g.players.append(gp)
    assert len(g.players) == 1


def test_game_rounds_relationship():
    g = Game(group_chat_id=-1)
    r = Round(game_id=1, round_number=1, letter="B")
    g.rounds.append(r)
    assert len(g.rounds) == 1
