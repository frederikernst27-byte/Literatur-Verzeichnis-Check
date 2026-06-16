#!/usr/bin/env python3
"""CLI: PDF eines Literaturverzeichnisses prüfen und als Excel exportieren.

Beispiele:
    python cli.py abschlussarbeit.pdf
    python cli.py abschlussarbeit.pdf --pages 45-50 -o report.xlsx
    python cli.py abschlussarbeit.pdf --use-ai --provider gemini
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from src.pipeline import run_pipeline_to_excel
from src.verify.ai_search import AIProviderError


def parse_page_range(value: str) -> tuple[int, int]:
    start, _, end = value.partition("-")
    return int(start), int(end or start)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Literaturverzeichnis auf existierende/korrekte Quellen prüfen.")
    parser.add_argument("pdf", help="Pfad zur PDF-Datei der Abschlussarbeit")
    parser.add_argument("-o", "--output", default="literaturpruefung.xlsx", help="Pfad der Ausgabe-Excel-Datei")
    parser.add_argument("--pages", help="Seitenbereich des Literaturverzeichnisses, z.B. 45-50 (sonst Auto-Erkennung)")
    parser.add_argument("--use-ai", action="store_true", default=None, help="KI-Websuche als Fallback aktivieren")
    parser.add_argument("--no-ai", dest="use_ai", action="store_false", help="KI-Websuche deaktivieren (nur API-Prüfung)")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], help="KI-Provider (überschreibt AI_PROVIDER aus .env)")
    args = parser.parse_args()

    start_page = end_page = None
    if args.pages:
        start_page, end_page = parse_page_range(args.pages)

    try:
        output_path = run_pipeline_to_excel(
            args.pdf,
            args.output,
            start_page=start_page,
            end_page=end_page,
            use_ai=args.use_ai,
            ai_provider=args.provider,
        )
    except AIProviderError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fertig. Ergebnis: {output_path}")


if __name__ == "__main__":
    main()
