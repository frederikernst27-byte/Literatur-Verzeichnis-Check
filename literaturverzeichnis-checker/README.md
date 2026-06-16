# Literaturverzeichnis-Checker

Prüft das Literaturverzeichnis einer Abschlussarbeit (PDF) automatisiert:
existieren die zitierten Quellen wirklich, stimmen Autor/Jahr/Seitenangabe,
oder wurde die Quelle komplett erfunden ("halluziniert")? Ergebnis ist eine
Excel-Tabelle mit Status je Zitat.

> Hinweis: Dieses Tool ist ein Hilfsmittel, kein Beweis. Es liefert Indizien
> (z.B. Quellen, die in keiner akademischen Datenbank auffindbar sind), aber
> falsch-positive/-negative Treffer sind möglich - Ergebnisse mit Status
> "Unklar" oder "vermutlich halluziniert" sollten manuell gegengeprüft werden.

## Funktionsweise

1. **PDF einlesen**: Seiten des Literaturverzeichnisses werden automatisch
   erkannt (Überschrift "Literaturverzeichnis"/"References") oder per
   `--pages` manuell angegeben.
2. **Zitate parsen**: Text wird in einzelne Literaturangaben zerlegt
   (nummerierte Listen, APA-artige Formate).
3. **Verifikation**:
   - Immer (kostenlos, kein Key nötig): Abfrage bei **CrossRef**,
     **OpenAlex** und **Semantic Scholar**, Abgleich von Titel + Autoren.
   - Optional (`--use-ai`, per Default aus): KI-Websuche als Fallback,
     falls die APIs nichts finden.
4. **Excel-Export**: pro Zitat Status, gefundene Quelle, konkrete
   Abweichungen, Prüfmethode und Konfidenz.

### Status-Werte

| Status | Bedeutung |
|---|---|
| Gefunden - korrekt | Quelle eindeutig gefunden, keine Abweichungen |
| Gefunden - Abweichungen | Quelle gefunden, aber z.B. Jahr/Autor/Titel weicht ab |
| Unklar - manuelle Prüfung empfohlen | Nur unsicherer Treffer gefunden |
| Nicht gefunden - vermutlich halluziniert | Keine passende Quelle gefunden |

## Setup

```bash
cd literaturverzeichnis-checker
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` öffnen und bei Bedarf anpassen (siehe unten).

## Nutzung per Kommandozeile (CLI)

```bash
# Automatische Erkennung des Literaturverzeichnisses, nur API-Prüfung
python cli.py abschlussarbeit.pdf

# Bestimmter Seitenbereich, eigener Ausgabename
python cli.py abschlussarbeit.pdf --pages 45-50 -o pruefung.xlsx

# Mit KI-Websuche als Fallback (braucht API-Key, siehe unten)
python cli.py abschlussarbeit.pdf --use-ai --provider openrouter
python cli.py abschlussarbeit.pdf --use-ai --provider gemini
```

Ergebnis ist eine `.xlsx`-Datei mit allen geprüften Zitaten.

## KI-Fallback (optional)

Per Default ist die KI-Websuche **deaktiviert** (`USE_AI=false`) - es läuft
dann ausschließlich die kostenlose API-Prüfung gegen CrossRef/OpenAlex/
Semantic Scholar, ganz ohne API-Key. Man entscheidet bewusst, ob man die
KI-Stufe dazu schalten will:

- **OpenRouter** (Default-Provider): Account auf https://openrouter.ai
  anlegen (kostenlos), API-Key erzeugen, in `.env` bei
  `OPENROUTER_API_KEY` eintragen. In `OPENROUTER_MODEL` steht ein aktuell
  kostenloses Modell - auf https://openrouter.ai/models nach `:free`
  filtern, falls das hinterlegte Modell nicht mehr verfügbar ist. Für die
  Websuche wird automatisch die `:online`-Variante des Modells verwendet.
- **Gemini** (Alternative): API-Key in Google AI Studio
  (https://aistudio.google.com/apikey) erzeugen, in `.env` bei
  `GEMINI_API_KEY` eintragen, `AI_PROVIDER=gemini` setzen. Nutzt Gemini
  2.5 Flash mit Google-Search-Grounding.

## E-Mail-Bot (optional)

`email_bot.py` pollt ein Postfach per IMAP, prüft PDF-Anhänge automatisch
und schickt das Excel-Ergebnis als Antwortmail zurück.

### Postfach einrichten

1. Eigenes E-Mail-Konto für den Bot anlegen (z.B. ein separates Gmail-
   oder Uni-Postfach), das nicht für anderes genutzt wird.
2. IMAP und SMTP Zugangsdaten besorgen:
   - Bei Gmail: 2-Faktor-Auth aktivieren, dann ein "App-Passwort" unter
     https://myaccount.google.com/apppasswords erzeugen (normales Passwort
     funktioniert nicht).
   - Bei anderen Anbietern: IMAP/SMTP-Zugangsdaten aus den
     Postfacheinstellungen.
3. In `.env` eintragen: `IMAP_HOST`, `IMAP_PORT` (meist 993),
   `IMAP_USER`, `IMAP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT` (meist 587),
   `SMTP_USER`, `SMTP_PASSWORD`.

### Starten

```bash
python email_bot.py
```

Der Bot läuft dauerhaft (Polling-Intervall über `POLL_INTERVAL_SECONDS`,
Default 60s) und muss daher auf einem Rechner/Server laufen, der
durchgehend erreichbar ist - z.B.:

- Als Cron-Job, der den Prozess am Leben hält (oder `systemd`-Service),
- oder einfach manuell auf einem Uni-Rechner im Hintergrund (`nohup python
  email_bot.py &`) für gelegentliche Batch-Nutzung durch die Hiwis.

Mails an das Postfach mit PDF-Anhang werden automatisch verarbeitet, die
Antwort enthält die Ergebnis-Excel-Datei als Anhang.

## Tests

```bash
pytest
```

`tests/fixtures/` kann eigene Beispiel-PDFs mit bekannten echten und
bewusst erfundenen Quellen enthalten, um die Klassifikation manuell zu
prüfen (`python cli.py tests/fixtures/<datei>.pdf`).

## Grenzen

- Die Zitat-Erkennung (`parse_citations.py`) ist heuristisch (Regex-
  basiert) und deckt gängige Stile ab, aber nicht jeden denkbaren
  Zitationsstil perfekt.
- CrossRef/OpenAlex/Semantic Scholar decken vor allem wissenschaftliche
  Paper ab - Bücher, graue Literatur oder Webseiten werden schlechter
  gefunden (hier hilft der optionale KI-Fallback mit Websuche).
- Ein "Nicht gefunden"-Status ist ein Indiz, kein Beweis für eine
  Halluzination - z.B. sehr neue, sehr spezielle oder nicht-englische
  Quellen können ebenfalls in keiner API auftauchen.
