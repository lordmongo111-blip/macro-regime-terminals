# Macro / Regime Terminal — Starterprojekt

Deutsches Streamlit-Dashboard für G10-FX-Makro, Saisonalität, COT, NQ/ES und quantitative Analyse.

## Was enthalten ist

- Übersicht und Datenqualitäts-Hinweise
- G10-Währungs-Makro-Matrix (Bias bleibt unbestimmt, bis echte Daten angebunden sind)
- FRED-Abfrage für ausgewählte US-Makro-/Zinsserien
- Historische Saisonalität für FX- und Index-Futures-Proxies
- CFTC-Endpunkt-Test für COT-Daten
- Historische NQ-/ES-Preis-Ansicht
- Synthetische Regression zur Demonstration der Pipeline
- Quellenregister und Hinweise zur Aktualität

## Lokal starten

Benötigt Python 3.10 oder neuer.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Kostenlos online veröffentlichen (Streamlit Community Cloud)

1. Erstelle ein GitHub-Konto, falls du noch keines hast.
2. Entpacke dieses ZIP und lade die Dateien in ein neues GitHub-Repository hoch.
3. Öffne https://share.streamlit.io/ und verbinde GitHub.
4. Wähle das Repository, den Branch und `app.py`.
5. Klicke auf Deploy. Du erhältst eine URL unter `*.streamlit.app`.

Verfügbarkeit, Schlafverhalten und Limits des kostenlosen Hostings können sich ändern.

## FRED API-Key

FRED bietet kostenlose API-Keys nach Registrierung: https://fred.stlouisfed.org/docs/api/api_key.html

Zum Testen kann der Key im Seitenleistenfeld eingegeben werden. Für dauerhaftes Hosting besser unter **App settings → Secrets** speichern:

```toml
FRED_API_KEY = "DEIN_KEY"
```

Hinweis: Das Starterprojekt zeigt das Feld als optionale Eingabe; produktiv kann die App auf `st.secrets["FRED_API_KEY"]` umgestellt werden. Niemals Secrets in GitHub committen.

## Wichtige Datenhinweise

- Es ist **keine fertig deployte Website**; dieses ZIP ist das Projekt zum Hochladen.
- Es gibt keinen garantierten Echtzeitfeed. `yfinance` ist ein Community-Wrapper und Daten können verzögert, lückenhaft oder für Trading-Zwecke nicht lizenziert sein.
- FRED enthält viele offizielle Makro- und Zinsreihen, aber nicht jede gewünschte G10-Serie und keine vollständigen Konsensüberraschungen.
- CFTC COT misst Positionen in bestimmten Futures-Kontrakten, nicht alle globalen Spot-FX-Positionen. Contract IDs, Reporttyp und Felder müssen validiert werden.
- Saisonale Ergebnisse werden aus den tatsächlich abgerufenen historischen Kursen berechnet; Rollmethodik und Symbolverfügbarkeit beeinflussen Futures-Ergebnisse.
- NQ/ES-Proxies sind keine Zusicherung von Börsen-Echtzeitdaten.
- Keine Bullish-/Bearish-Signale werden als echt ausgegeben, solange valide Inputs fehlen. Vor realem Einsatz Datenqualität, Methodik, Lizenzen und Berechnungen testen.

## Dateien

- `app.py` — Dashboard
- `requirements.txt` — Python-Abhängigkeiten
- `README.md` — Setup und Hosting-Anleitung
- `.gitignore` — verhindert versehentliches Committen lokaler Secrets/Umgebungen
