import asyncio
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)

_HEALTH_PORT = 9090


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._health()
        elif self.path == "/metrics":
            self._metrics()
        else:
            self.send_response(404)
            self.end_headers()

    def _health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = json.dumps(
            {
                "status": "ok",
                "service": "stop-bot-game",
                "version": "1.0.0",
            }
        ).encode()
        self.wfile.write(data)

    def _metrics(self):
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.end_headers()
        self.wfile.write(generate_latest())

    def log_message(self, format, *args):
        logger.debug("HealthServer: %s", format % args)


async def start_health_server(port: int = _HEALTH_PORT) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, server.serve_forever)
    return server


def run_health_server_sync(port: int = _HEALTH_PORT) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    logger.info("Health server iniciado en puerto %s", port)
    return server
