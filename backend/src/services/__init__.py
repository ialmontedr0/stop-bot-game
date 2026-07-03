from .game_orchestrator import LobbyManager
from .score_engine import ScoreEngine
from .spell_corrector import SpellCorrector, get_corrector
from .leaderboard import LeaderboardService
from .round_manager import RoundManager, round_manager

# Singleton del corrector ortografico (lazy, sin circular imports)
spell_corrector = get_corrector()

__all__ = [
    "LobbyManager",
    "ScoreEngine",
    "SpellCorrector",
    "LeaderboardService",
    "RoundManager",
    "round_manager",
    "spell_corrector",
]
