# Literatur-Verzeichnis-Check

Prüft das Literaturverzeichnis einer Abschlussarbeit (PDF) automatisiert auf
mögliche halluzinierte/erfundene Quellen. Details zur Funktionsweise, CLI-
Nutzung und zum E-Mail-Bot siehe
[`literaturverzeichnis-checker/README.md`](literaturverzeichnis-checker/README.md).

## Website (Vercel)

`public/index.html` ist ein einfaches Web-Frontend (PDF hochladen -> Excel-
Ergebnis herunterladen), `api/check.py` die zugehörige Python-Serverless-
Function. Beides nutzt direkt den Code aus `literaturverzeichnis-checker/`.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/import?s=https://github.com/frederikernst27-byte/Literatur-Verzeichnis-Check)

Per Klick auf den Button (oder im Vercel-Dashboard unter "Add New -> Project"
dieses GitHub-Repo auswählen) importiert Vercel das Repo und deployed automatisch -
`vercel.json` und `requirements.txt` sind bereits vorbereitet, es muss nichts
konfiguriert werden. Jeder Push auf `main` deployed danach automatisch neu.

Alternativ per CLI (erfordert Login im Browser):

```bash
npm i -g vercel
vercel login
vercel --prod
```

Hinweise:
- Die Web-Variante läuft ohne KI-Fallback (`use_ai=False`) - nur die
  kostenlosen APIs (CrossRef/OpenAlex/Semantic Scholar), kein API-Key nötig.
- Bei sehr langen Literaturverzeichnissen kann die Prüfung das
  Funktions-Timeout (`vercel.json`, aktuell 60s) überschreiten - dann lieber
  die CLI lokal nutzen.
- GitHub Pages funktioniert hier nicht, da die Prüfung serverseitigen Python-
  Code (PDF-Parsing, externe API-Aufrufe, Excel-Export) braucht - Pages kann
  nur statische Dateien ausliefern.
