from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import generate_latest

from src.monitoring import metrics
from src.monitoring.health_server import (
    MetricsHandler,
    run_health_server_sync,
    start_health_server,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics.games_started._value.set(0)
    metrics.games_finished._value.set(0)
    metrics.rounds_played._value.set(0)
    metrics.messages_sent._value.set(0)
    metrics.player_joins._value.set(0)
    metrics.active_games.set(0)
    metrics.active_players.set(0)
    metrics.db_pool_size.set(0)
    metrics.redis_connected.set(0)
    yield


class TestMetricsModule:
    def test_counters_increment(self):
        metrics.games_started.inc()
        metrics.games_finished.inc()
        metrics.rounds_played.inc()
        metrics.messages_sent.inc()
        metrics.player_joins.inc()
        assert float(metrics.games_started._value.get()) == 1
        assert float(metrics.games_finished._value.get()) == 1
        assert float(metrics.rounds_played._value.get()) == 1

    def test_labeled_counters(self):
        metrics.api_calls_total.labels(provider="openai").inc(3)
        metrics.errors_total.labels(type="ValueError").inc()
        assert float(metrics.api_calls_total.labels(provider="openai")._value.get()) == 3
        assert float(metrics.errors_total.labels(type="ValueError")._value.get()) == 1

    def test_gauges(self):
        metrics.active_games.set(5)
        metrics.active_players.set(20)
        metrics.db_pool_size.set(10)
        metrics.redis_connected.set(1)
        assert float(metrics.active_games._value.get()) == 5
        assert float(metrics.active_players._value.get()) == 20
        assert float(metrics.redis_connected._value.get()) == 1

    def test_observe_functions(self):
        metrics.observe_round_duration(30.0)
        metrics.observe_game_duration(10.0)
        metrics.observe_api_call("openai", 1.5)
        metrics.observe_api_call("groq", 2.0)

    def test_generate_latest_includes_all_metrics(self):
        metrics.games_started.inc()
        metrics.active_games.set(3)
        output = generate_latest()
        assert b"stopbot_games_started_total" in output
        assert b"stopbot_active_games" in output
        assert b"stopbot_round_duration_seconds" in output


class TestHealthServer:
    def _make_handler(self):
        inst = MetricsHandler.__new__(MetricsHandler)
        inst.request = MagicMock()
        inst.request_version = "HTTP/1.0"
        inst.command = "GET"
        inst.path = "/health"
        inst.headers = {}
        inst.rfile = MagicMock()
        inst.wfile = MagicMock()
        inst.client_address = ("127.0.0.1", 12345)
        inst.server = MagicMock()
        inst.close_connection = False
        inst.raw_requestline = b"GET /health HTTP/1.0\r\n"
        inst.requestline = "GET /health HTTP/1.0"
        return inst

    def test_health_returns_json(self):
        inst = self._make_handler()
        inst.path = "/health"
        inst.do_GET()
        data = b"".join(c[0][0] for c in inst.wfile.write.call_args_list)
        assert b"status" in data
        assert b"ok" in data
        assert b"stop-bot-game" in data

    def test_metrics_returns_prometheus(self):
        metrics.games_started.inc()
        inst = self._make_handler()
        inst.path = "/metrics"
        inst.do_GET()
        data = b"".join(c[0][0] for c in inst.wfile.write.call_args_list)
        assert b"stopbot_games_started_total" in data

    def test_unknown_path_returns_404(self):
        inst = self._make_handler()
        inst.path = "/unknown"
        inst.do_GET()
        assert inst.responses[404] is not None

    def test_log_message_debug(self):
        inst = self._make_handler()
        with patch("src.monitoring.health_server.logger") as mock_log:
            inst.log_message("GET %s", "/health")
            mock_log.debug.assert_called_once()

    def test_start_health_server(self):
        from src.monitoring.health_server import start_health_server, run_health_server_sync

        with patch("src.monitoring.health_server.HTTPServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            coro = start_health_server(port=9999)
            task = loop.create_task(coro)
            loop.call_soon(task.cancel)
            loop.run_until_complete(asyncio.sleep(0.1))
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
            loop.close()
            mock_server_cls.assert_called_once_with(("0.0.0.0", 9999), MetricsHandler)

    def test_run_health_server_sync(self):
        with patch("src.monitoring.health_server.HTTPServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server
            run_health_server_sync(port=9998)
            mock_server_cls.assert_called_once_with(("0.0.0.0", 9998), MetricsHandler)
            mock_server.serve_forever.assert_called_once()
