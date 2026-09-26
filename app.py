import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from db import init_db, seed_rfqs
from routes import bp as api_bp

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    init_db()
    seed_rfqs()
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        if (e.code or 500) >= 500:
            logger.exception("HTTP %s on %s", e.code, request.path)
        return jsonify({"error": e.name, "detail": e.description}), e.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        logger.exception("unhandled exception on request")
        return jsonify({"error": "internal server error", "detail": str(e)}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
