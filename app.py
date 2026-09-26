import os

from dotenv import load_dotenv
from flask import Flask, send_from_directory

from db import init_db, seed_rfqs
from routes import bp as api_bp

load_dotenv()


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    init_db()
    seed_rfqs()
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
