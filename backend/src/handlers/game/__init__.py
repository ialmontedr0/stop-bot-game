# Router para logica del juego
from .diagnose import diagnose_router
from .lobby import game_router
from .round import round_router

__all__ = ["game_router", "round_router", "diagnose_router"]
