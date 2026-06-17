import os
import sys
import tempfile
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "literaturverzeichnis-checker"))

from flask import Flask, jsonify, request, send_file  # noqa: E402

from src.pipeline import has_server_ai_key, run_pipeline_to_excel  # noqa: E402

app = Flask(__name__)

ALLOWED_BLOB_HOSTS_SUFFIX = ".public.blob.vercel-storage.com"


@app.route("/api/ai-status", methods=["GET"])
def ai_status():
    return jsonify({"hasKey": has_server_ai_key()})


@app.route("/", methods=["POST"])
@app.route("/api/check", methods=["POST"])
def check():
    pdf_file = request.files.get("pdf")
    blob_url = None
    json_body = {}
    if request.is_json:
        json_body = request.get_json(silent=True) or {}
        blob_url = json_body.get("blob_url")
    blob_url = blob_url or request.form.get("blob_url")

    if not pdf_file and not blob_url:
        return jsonify({"error": "Keine PDF-Datei hochgeladen."}), 400

    start_page = request.form.get("start_page") or request.args.get("start_page") or json_body.get("start_page")
    end_page = request.form.get("end_page") or request.args.get("end_page") or json_body.get("end_page")

    # KI-Modus: use_ai aus dem Request
    use_ai_raw = json_body.get("use_ai") or request.form.get("use_ai")
    if use_ai_raw is not None:
        use_ai = str(use_ai_raw).lower() in ("true", "1", "yes")
    else:
        use_ai = None  # Pipeline liest USE_AI aus der Umgebung

    # Nutzer-eigener OpenRouter-Key (Fallback wenn Server keinen Key hat)
    openrouter_api_key = (
        json_body.get("openrouter_api_key") or request.form.get("openrouter_api_key")
        or json_body.get("gemini_api_key") or request.form.get("gemini_api_key")  # legacy
        or None
    )
    if openrouter_api_key is not None:
        openrouter_api_key = openrouter_api_key.strip() or None

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "input.pdf")

        if blob_url:
            host = urlparse(blob_url).netloc
            if not host.endswith(ALLOWED_BLOB_HOSTS_SUFFIX):
                return jsonify({"error": "Ungültige Datei-URL."}), 400
            try:
                resp = requests.get(blob_url, timeout=55)
                resp.raise_for_status()
            except requests.RequestException as e:
                return jsonify({"error": f"Datei konnte nicht geladen werden: {e}"}), 400
            with open(pdf_path, "wb") as f:
                f.write(resp.content)
        else:
            pdf_file.save(pdf_path)

        out_path = os.path.join(tmp, "ergebnis.xlsx")
        try:
            run_pipeline_to_excel(
                pdf_path,
                out_path,
                start_page=int(start_page) if start_page else None,
                end_page=int(end_page) if end_page else None,
                use_ai=use_ai,
                ai_provider="openrouter",
                openrouter_api_key=openrouter_api_key,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return send_file(
            out_path,
            as_attachment=True,
            download_name="literaturpruefung.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
