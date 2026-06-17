import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "literaturverzeichnis-checker"))

from flask import Flask, jsonify  # noqa: E402

from src.pipeline import has_server_ai_key  # noqa: E402

app = Flask(__name__)


@app.route("/api/ai-status", methods=["GET"])
@app.route("/", methods=["GET"])
def ai_status():
    return jsonify({"hasKey": has_server_ai_key()})
