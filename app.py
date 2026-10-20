import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Macro / Regime Terminal", page_icon="⌁", layout="wide")

G10 = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {background: rgba(120,130,120,.08); padding: 12px; border-radius: 12px;}
.small-muted {color: #7c8982; font-size: .85rem;}
</style>
""", unsafe_allow_html=True)

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def get_fred_series(series_id, api_key, observation_start="2015-01-01"):
    """Fetch FRED observations server-side. Requires a free FRED API key."""
    import requests
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": observation_start, "sort_order": "asc"
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    observations = response.json().get("observations", [])
    df = pd.DataFrame(observations)
    if df.empty:
        return pd.DataFrame(columns=["date", "value"])
    df = df[df["value"] != "."].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", "value"]].dropna()

def load_market_history(symbol, period="10y"):
    """Historical price helper via yfinance; availability/terms depend on symbol/provider."""
    import yfinance as yf
    data = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False)
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].iloc[:, 0]
    else:
        close = data["Close"]
    out = close.rename("close").to_frame().dropna()
    out.index = pd.to_datetime(out.index)
    out.index.name = "date"
    return out.reset_index()

def seasonality(df):
    if df.empty or "close" not in df:
        return pd.DataFrame()
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date")
    d["month"] = d["date"].dt.month
    # Monthly close-to-close returns, grouped by calendar month over available history.
    monthly = d.set_index("date")["close"].resample("ME").last().dropna().pct_change().dropna().to_frame("return")
    monthly["month"] = monthly.index.month
    return monthly.groupby("month")["return"].agg(
        avg_return="mean",
        win_rate=lambda x: (x > 0).mean(),
        observations="count",
        median="median",
        volatility="std"
    ).reset_index()

def cot_api_preview():
    """Official CFTC Socrata API query: latest available records vary by dataset."""
    import requests
    # Public CFTC Legacy Futures Only dataset. Querying schema can change; fail visibly.
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    params = {"$limit": 5, "$order": "report_date_as_yyyy_mm_dd DESC"}
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return pd.DataFrame(response.json())

st.title("⌁ MACRO / REGIME TERMINAL")
st.caption("G10 FX · Makro · COT · Saisonalität · NQ / ES · Quant — Starter-Projekt")
st.warning("Datenstatus: Ohne konfigurierte Datenquelle werden keine aktuellen Marktmeinungen behauptet. Historische Daten sind nicht automatisch Echtzeitdaten; Anbieter, Verzögerung und Lizenzbedingungen beachten.")

with st.sidebar:
    st.header("Einstellungen")
    page = st.radio("Modul", ["Übersicht", "FX Macro", "Saisonalität", "COT / Positioning", "NQ & ES", "Quant & Regression", "Datenquellen"])
    st.divider()
    fred_key = st.text_input("FRED API-Key (optional)", type="password", help="Wird serverseitig in dieser Streamlit-Sitzung verwendet. Für Deployment besser Streamlit Secrets nutzen.")
    st.caption(f"Ansicht erstellt: {utc_now()}")
    st.caption("Build: Starter v1.0 · Daten müssen geprüft werden.")

# Demo values are intentionally labeled and are not market data.
demo_strength = pd.DataFrame({
    "Währung": G10,
    "Score": [0.8, 0.3, 0.5, -0.9, 0.1, 0.2, -0.4, -0.6]
})
demo_strength["Status"] = "DEMO"

if page == "Übersicht":
    st.subheader("Cross-Asset Überblick")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Risk regime", "UNBESTIMMT", help="Wird erst nach Verbindung valider Inputs berechnet.")
    k2.metric("Stärkste CCY", "—")
    k3.metric("Schwächste CCY", "—")
    k4.metric("Datenqualität", "OHNE FEED")
    st.info("Hier werden keine Demo-Scores als aktuelle Marktmeinung dargestellt. Verbinde unten Datenquellen, bevor du Signale nutzt.")
    st.markdown("#### Gewünschte Module")
    st.write("G10-Währungsstärke · Rates/Inflation/Arbeitsmarkt/Bonds · COT · Monats-Saisonalität · NQ/ES · Regression · Risiko-Regime · Bull-/Bear-Szenarien")
    st.markdown("#### Start-Checkliste")
    st.write("- [ ] FRED API-Key für Makro- und Zinsserien hinterlegen")
    st.write("- [ ] Historische Preise für FX, NQ und ES abrufen und Datenqualität prüfen")
    st.write("- [ ] CFTC-Kontrakte/Kategorien korrekt zuordnen")
    st.write("- [ ] Regeln und Schwellenwerte testen, bevor Signale produktiv genutzt werden")

elif page == "FX Macro":
    st.subheader("G10 Currency Macro")
    st.caption("Noch kein Live-Bias. Die Tabelle ist ein Datenmodell für die spätere Berechnung.")
    fx = pd.DataFrame({
        "CCY": G10,
        "Policy / rates": ["Nicht verbunden"]*8,
        "Inflation": ["Nicht verbunden"]*8,
        "Labour": ["Nicht verbunden"]*8,
        "Bonds": ["Nicht verbunden"]*8,
        "COT": ["Nicht verbunden"]*8,
        "Seasonality": ["Nicht verbunden"]*8,
        "Bias": ["UNBESTIMMT"]*8,
        "Confidence": ["—"]*8,
    })
    st.dataframe(fx, use_container_width=True, hide_index=True)
    st.markdown("#### Makro-Daten über FRED testen")
    st.caption("Beispielserie: FEDFUNDS = effektiver US-Leitzins; CPIAUCSL = US-CPI-Index; UNRATE = Arbeitslosenquote; DGS10 = US Treasury 10Y.")
    series_id = st.selectbox("FRED-Serie", ["FEDFUNDS", "CPIAUCSL", "UNRATE", "DGS10", "DGS2", "T10YIE"])
    if st.button("FRED-Serie laden"):
        if not fred_key:
            st.error("Bitte einen FRED API-Key in der Seitenleiste eintragen. Kostenlos registrierbar bei FRED.")
        else:
            try:
                df = get_fred_series(series_id, fred_key)
                if df.empty:
                    st.warning("Keine Beobachtungen zurückgegeben.")
                else:
                    st.success(f"{len(df)} Beobachtungen geladen. Letzter Datenpunkt: {df.iloc[-1]['date'].date()} — Wert {df.iloc[-1]['value']}")
                    st.line_chart(df.set_index("date")["value"])
                    st.dataframe(df.tail(10), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"FRED-Abfrage fehlgeschlagen: {e}")

elif page == "Saisonalität":
    st.subheader("Monatliche Saisonalität")
    symbols = {
        "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X",
        "AUD/USD": "AUDUSD=X", "NQ (Nasdaq-100 proxy)": "NQ=F", "ES (S&P 500 proxy)": "ES=F"
    }
    label = st.selectbox("Instrument / Proxy", list(symbols))
    years = st.selectbox("Historie", ["5y", "10y", "max"], index=1)
    if st.button("Historische Daten laden und berechnen"):
        with st.spinner("Lade historische Daten…"):
            try:
                prices = load_market_history(symbols[label], years)
                if prices.empty:
                    st.error("Keine Daten erhalten. Symbol oder Anbieter prüfen.")
                else:
                    result = seasonality(prices)
                    result["Monat"] = result["month"].map(lambda m: MONTHS[int(m)-1])
                    result["Ø Rendite (%)"] = result["avg_return"] * 100
                    result["Positive Jahre (%)"] = result["win_rate"] * 100
                    st.caption(f"Quelle: yfinance/Yahoo Finance Wrapper · Abruf {utc_now()} · Historische Daten, kein garantierter Echtzeitfeed. Symbol: {symbols[label]}")
                    fig = px.bar(result, x="Monat", y="Ø Rendite (%)", color="Ø Rendite (%)", title=f"{label} — durchschnittliche Monatsrendite")
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(result[["Monat", "Ø Rendite (%)", "Positive Jahre (%)", "observations", "median", "volatility"]], use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Download/Berechnung fehlgeschlagen: {e}")
    else:
        st.info("Klicke auf „Historische Daten laden und berechnen“, um Saisonalität aus historischen Kursdaten zu berechnen. Die Daten sind nicht garantiert vollständig oder börsenoffiziell.")

elif page == "COT / Positioning":
    st.subheader("COT / Positioning")
    st.caption("CFTC-Daten sind Futures-Positionierung, nicht der gesamte globale Spot-FX-Markt. Contract code mapping muss je Datensatz geprüft werden.")
    if st.button("CFTC-Datenquelle testen"):
        try:
            cot = cot_api_preview()
            st.success(f"Antwort erhalten: {len(cot)} Datensätze. Vor Verwendung unbedingt Spalten, Reporttyp und Kontraktzuordnung validieren.")
            st.dataframe(cot, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"CFTC-Abfrage nicht verfügbar oder Schema geändert: {e}")
    st.markdown("#### Kontrakte für FX-Recherche")
    st.dataframe(pd.DataFrame([
        ["EUR", "Euro FX", "6E"], ["GBP", "British Pound", "6B"], ["JPY", "Japanese Yen", "6J"],
        ["CAD", "Canadian Dollar", "6C"], ["AUD", "Australian Dollar", "6A"],
        ["CHF", "Swiss Franc", "6S"], ["NZD", "New Zealand Dollar", "6N"], ["USD", "Kein einzelner direkter G10-COT-Proxy", "—"]
    ], columns=["Währung", "CFTC-Futures-Kontrakt", "Ticker/Code"]), use_container_width=True, hide_index=True)
    st.warning("Der CFTC-Endpunkt und seine Felder können sich ändern. Vor produktiver Nutzung Reporttyp (Legacy/Disaggregated/TFF), Datenfelder, Berichtswoche und Kontrakt-ID validieren.")

elif page == "NQ & ES":
    st.subheader("NQ & ES Macro Lens")
    symbols = {"NQ=F": "Nasdaq-100 Futures (Datenanbieter-Symbol)", "ES=F": "S&P 500 Futures (Datenanbieter-Symbol)"}
    symbol = st.selectbox("Historisches Symbol", list(symbols), format_func=lambda x: symbols[x])
    period = st.selectbox("Zeitraum", ["3mo", "1y", "5y"], index=1)
    if st.button("Historie laden"):
        try:
            df = load_market_history(symbol, period)
            if df.empty:
                st.error("Keine historischen Preise erhalten.")
            else:
                st.caption(f"Historischer Preis-Proxy · Abruf {utc_now()} · keine Zusicherung von Echtzeit oder Börsenlizenz.")
                st.line_chart(df.set_index("date")["close"])
                df["return_pct"] = df["close"].pct_change()*100
                st.dataframe(df.tail(10), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Marktdaten konnten nicht geladen werden: {e}")
    st.markdown("#### Makro-Checkliste")
    st.write("- US-Realrenditen / Treasury yields")
    st.write("- Fed-Erwartungen und Inflationsüberraschungen")
    st.write("- Marktbreite, Volatilität und Kreditspreads")
    st.write("- Earnings breadth / Revisionen")
    st.info("NQ-/ES-Futures-Symbole über kostenlose Wrapper können verzögert, unvollständig oder anders gerollt sein. Für Trading-Anwendungen Broker- oder lizenzierte Börsendaten nutzen.")

elif page == "Quant & Regression":
    st.subheader("Quant & Regression")
    st.caption("Demo-Regression wird aus synthetischen Daten gerechnet und ist keine Marktaussage.")
    rng = np.random.default_rng(42)
    n = st.slider("Beobachtungen", 30, 500, 120, 10)
    x = rng.normal(0, 1, n)
    y = -0.45*x + rng.normal(0, 0.8, n)
    fit = np.polyfit(x, y, 1)
    pred = np.polyval(fit, x)
    ss_res = np.sum((y-pred)**2)
    ss_tot = np.sum((y-y.mean())**2)
    r2 = 1 - ss_res/ss_tot
    c1, c2, c3 = st.columns(3)
    c1.metric("Beta (synthetisch)", f"{fit[0]:.3f}")
    c2.metric("R² (synthetisch)", f"{r2:.3f}")
    c3.metric("Observations", n)
    plot_df = pd.DataFrame({"x": x, "y": y, "OLS": pred}).sort_values("x")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="Synthetische Punkte", opacity=.6))
    fig.add_trace(go.Scatter(x=plot_df["x"], y=plot_df["OLS"], mode="lines", name="OLS-Linie"))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("#### Risk regime inputs")
    st.write("Noch nicht bewertet: Aktienbreite, Realrenditen, Kreditspreads, Dollartrend, Volatilität. Keine Risk-on/off-Klassifikation ohne verifizierte Inputs.")

else:
    st.subheader("Datenquellen & Aktualität")
    st.markdown("#### Quellenregister")
    sources = pd.DataFrame([
        ["Makro/Zinsen", "FRED API", "API-Key nötig; Frequenz je Serie; kein Konsenssurprise ohne Zusatzanbieter"],
        ["Zentralbankpfade", "Fed, EZB, BoE, BoJ, SNB, BoC, RBA, RBNZ", "Offizielle Veröffentlichungen; Parsing/Mapping erforderlich"],
        ["COT", "CFTC Public Reporting", "Wöchentlich; Reporttyp und Contract mapping validieren"],
        ["Historische Preise", "yfinance Wrapper / Yahoo Finance", "Nicht garantiert offiziell, vollständig, lizenziert oder echtzeitfähig"],
        ["NQ / ES live", "Broker oder lizenzierter Marktdatenanbieter", "API/Account und Lizenzbedingungen abhängig vom Anbieter"],
        ["Konsensdaten", "Separater Makro-Kalender-Anbieter", "Meist separat/lizenziert"]
    ], columns=["Bereich", "Quelle", "Hinweis"])
    st.dataframe(sources, use_container_width=True, hide_index=True)
    st.markdown("#### Freshness-Regeln für Produktion")
    st.write("- Jede Beobachtung braucht Quelle, Zeitstempel, Einheit und Frequenz.")
    st.write("- Fehlende/veraltete Daten dürfen nicht stillschweigend durch Nullen ersetzt werden.")
    st.write("- Jedes Signal muss auf die tatsächlich verwendeten Datenpunkte zurückführbar sein.")
    st.write("- API-Schlüssel in Streamlit Secrets oder Server-Umgebung speichern, niemals in öffentliche Frontend-Dateien.")
    st.markdown("#### FRED API-Key konfigurieren")
    st.code('[secrets.toml]\nFRED_API_KEY = "dein_api_key"', language="toml")
    st.caption("Die Beispielabfrage akzeptiert den Schlüssel im Sidebar-Feld. Für dauerhaftes Hosting besser st.secrets verwenden und das Secret nicht ins GitHub-Repository hochladen.")

st.divider()
st.caption("Macro / Regime Terminal — Starterprojekt. Keine Anlageberatung. Vor Live-Einsatz Datenlizenzen, Methodik, Kontraktrollen, Zeitstempel und Signale validieren.")
