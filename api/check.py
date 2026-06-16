import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "literaturverzeichnis-checker"))

from flask import Flask, jsonify, request, send_file  # noqa: E402

from src.pipeline import run_pipeline_to_excel  # noqa: E402

app = Flask(__name__)


@app.route("/", methods=["POST"])
@app.route("/api/check", methods=["POST"])
def check():
    pdf = request.files.get("pdf")
    if not pdf or not pdf.filename:
        return jsonify({"error": "Keine PDF-Datei hochgeladen."}), 400

    start_page = request.form.get("start_page") or None
    end_page = request.form.get("end_page") or None

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "input.pdf")
        pdf.save(pdf_path)
        out_path = os.path.join(tmp, "ergebnis.xlsx")
        try:
            run_pipeline_to_excel(
                pdf_path,
                out_path,
                start_page=int(start_page) if start_page else None,
                end_page=int(end_page) if end_page else None,
                use_ai=False,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return send_file(
            out_path,
            as_attachment=True,
            download_name="literaturpruefung.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
