# Literatur-Verzeichnis-Check

Prüft das Literaturverzeichnis einer Abschlussarbeit (PDF) automatisiert auf
mögliche halluzinierte/erfundene Quellen. Details zur Funktionsweise, CLI-
Nutzung und zum E-Mail-Bot siehe
[`literaturverzeichnis-checker/README.md`](literaturverzeichnis-checker/README.md).

## Website (Vercel)

`public/index.html` ist ein einfaches Web-Frontend (PDF hochladen -> Excel-
Ergebnis herunterladen), `api/check.py` die zugehörige Python-Serverless-
Function. Beides nutzt direkt den Code aus `literaturverzeichnis-checker/`.

Deploy auf Vercel:

```bash
npm i -g vercel
vercel
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
