# app/__init__.py
from __future__ import annotations
import os
from flask import Flask
from .app import init_app

def create_app() -> Flask:
    app = Flask(__name__)
    # Config
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key")
    app.config["REPORTS_DIR"] = os.path.abspath(os.environ.get("REPORTS_DIR", "Reportes"))
    app.config["ENABLE_PDF"] = os.environ.get("ENABLE_PDF", "true").lower() == "true"
    app.config["CURRENCY_SYMBOL"] = os.environ.get("CURRENCY_SYMBOL", "$")
    app.config["MAX_CONTENT_LENGTH"] = int(float(os.environ.get("MAX_UPLOAD_MB", "15"))) * 1024 * 1024
    app.config["APP_LOCALE"] = os.environ.get("APP_LOCALE", "es_AR")
    init_app(app)
    return app
