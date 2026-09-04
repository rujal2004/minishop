import json
import logging
import os
import socket
import time
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from config import Config
from models import create_database, seed_database
from routes import routes


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "minishop",
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload)


class Metrics:
    def __init__(self, host, port, enabled=True):
        self.address = (host, port)
        self.enabled = enabled
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def increment(self, name, tags=None):
        if not self.enabled:
            return
        tag_text = "|#" + ",".join(f"{key}:{value}" for key, value in (tags or {}).items())
        try:
            self.socket.sendto(f"minishop.{name}:1|c{tag_text}".encode(), self.address)
        except OSError:
            logging.getLogger("minishop").warning(
                "metrics_send_failed", extra={"fields": {"metric": name}}
            )


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("minishop")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    logger = configure_logging()
    app.logger = logger
    app.metrics = Metrics(
        app.config["DD_AGENT_HOST"],
        app.config["DD_DOGSTATSD_PORT"],
        app.config["DD_STATSD_ENABLED"],
    )
    app.engine, app.session_factory = create_database(app.config["DATABASE_URL"])
    seed_database(app.session_factory)
    app.register_blueprint(routes)

    @app.before_request
    def start_request():
        g.started_at = time.perf_counter()

    @app.after_request
    def observe_request(response):
        if request.path.startswith("/api/"):
            duration_ms = round((time.perf_counter() - g.started_at) * 1000, 2)
            status = response.status_code
            endpoint = request.endpoint or request.path
            app.metrics.increment("requests", {"endpoint": endpoint, "status": status})
            logger.info(
                "api_request",
                extra={"fields": {"endpoint": endpoint, "status": status, "duration_ms": duration_ms}},
            )
        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        endpoint = request.endpoint or request.path
        logger.warning(
            "http_error",
            extra={"fields": {"endpoint": endpoint, "status": error.code}},
        )
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    @app.errorhandler(Exception)
    def handle_exception(error):
        logger.exception(
            "unhandled_exception",
            extra={"fields": {"endpoint": request.endpoint or request.path, "status": 500}},
        )
        if request.path.startswith("/api/"):
            return jsonify(error="internal server error"), 500
        return "Internal server error", 500

    logger.info("application_started", extra={"fields": {"database": app.config["DATABASE_URL"]}})
    return app


if __name__ == "__main__":
    create_app().run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )