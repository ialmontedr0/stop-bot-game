from .error_tracker import ErrorTracker, error_tracker
from .game_orchestrator import LobbyManager
from .leaderboard import LeaderboardService
from .round_manager import RoundManager, round_manager
from .score_engine import ScoreEngine
from .spell_corrector import SpellCorrector, get_corrector

# Singleton del corrector ortografico (lazy, sin circular imports)
spell_corrector = get_corrector()

__all__ = [
    "ErrorTracker",
    "error_tracker",
    "LobbyManager",
    "ScoreEngine",
    "SpellCorrector",
    "LeaderboardService",
    "RoundManager",
    "round_manager",
    "spell_corrector",
]
