from prometheus_client import Counter, Gauge, Histogram

games_started = Counter(
    "stopbot_games_started_total",
    "Total de partidas iniciadas",
)

games_finished = Counter(
    "stopbot_games_finished_total",
    "Total de partidas finalizadas",
)

rounds_played = Counter(
    "stopbot_rounds_played_total",
    "Total de rondas jugadas",
)

api_calls_total = Counter(
    "stopbot_api_calls_total",
    "Total de llamadas a APIs externas",
    ["provider"],
)

errors_total = Counter(
    "stopbot_errors_total",
    "Total de errores capturados",
    ["type"],
)

messages_sent = Counter(
    "stopbot_messages_sent_total",
    "Total de mensajes enviados por el bot",
)

player_joins = Counter(
    "stopbot_player_joins_total",
    "Total de jugadores que se unieron a partidas",
)

round_duration_seconds = Histogram(
    "stopbot_round_duration_seconds",
    "Duracion de rondas en segundos",
    buckets=[5, 10, 15, 20, 30, 45, 60, 90, 120],
)

game_duration_minutes = Histogram(
    "stopbot_game_duration_minutes",
    "Duracion de partidas en minutos",
    buckets=[1, 3, 5, 10, 15, 20, 30],
)

api_call_duration_seconds = Histogram(
    "stopbot_api_call_duration_seconds",
    "Duracion de llamadas a APIs externas",
    ["provider"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

active_games = Gauge(
    "stopbot_active_games",
    "Numero de partidas activas actualmente",
)

active_players = Gauge(
    "stopbot_active_players",
    "Numero de jugadores en partidas actualmente",
)

db_pool_size = Gauge(
    "stopbot_db_pool_size",
    "Tamano del pool de conexiones a BD",
)

redis_connected = Gauge(
    "stopbot_redis_connected",
    "1 si Redis esta conectado, 0 si no",
)


def observe_round_duration(seconds: float) -> None:
    round_duration_seconds.observe(seconds)


def observe_game_duration(minutes: float) -> None:
    game_duration_minutes.observe(minutes)


def observe_api_call(provider: str, seconds: float) -> None:
    api_call_duration_seconds.labels(provider=provider).observe(seconds)
