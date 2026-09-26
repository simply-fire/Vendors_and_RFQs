import os

from dotenv import load_dotenv
from flask import Flask

from db import init_db, seed_rfqs

load_dotenv()


def create_app():
    app = Flask(__name__)
    init_db()
    seed_rfqs()
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
