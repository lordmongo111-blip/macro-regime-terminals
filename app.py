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

# ---------------- FX signal engine: fail closed on missing/invalid inputs ----------------
FX_PAIRS = {
    "EUR/USD": {"symbol": "EURUSD=X", "base": "EUR", "quote": "USD", "cot": "6E"},
    "GBP/USD": {"symbol": "GBPUSD=X", "base": "GBP", "quote": "USD", "cot": "6B"},
    "USD/JPY": {"symbol": "JPY=X", "base": "USD", "quote": "JPY", "cot": "6J"},
    "AUD/USD": {"symbol": "AUDUSD=X", "base": "AUD", "quote": "USD", "cot": "6A"},
    "USD/CAD": {"symbol": "CAD=X", "base": "USD", "quote": "CAD", "cot": "6C"},
    "USD/CHF": {"symbol": "CHF=X", "base": "USD", "quote": "CHF", "cot": "6S"},
    "NZD/USD": {"symbol": "NZDUSD=X", "base": "NZD", "quote": "USD", "cot": "6N"},
}
LONG_SHORT_THRESHOLD = 20
MAX_PRICE_AGE_DAYS = 4
MIN_PRICE_OBSERVATIONS = 220


def validate_price_history(df, max_age_days=MAX_PRICE_AGE_DAYS):
    """Validate real provider-returned daily prices; never create replacement data."""
    if df is None or df.empty or not {"date", "close"}.issubset(df.columns):
        return False, "Kursreihe fehlt", None
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], utc=True, errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values("date")
    if len(d) < MIN_PRICE_OBSERVATIONS:
        return False, f"Zu wenig Historie ({len(d)}/{MIN_PRICE_OBSERVATIONS} Tageswerte)", None
    if (d["close"] <= 0).any() or d["date"].duplicated().any():
        return False, "Ungültige Kurse oder doppelte Zeitstempel", None
    age = (pd.Timestamp.now(tz="UTC") - d["date"].iloc[-1]).total_seconds() / 86400
    if age > max_age_days:
        return False, f"Kursdaten veraltet ({age:.1f} Tage)", None
    return True, f"Validiert · {len(d)} Tageswerte · letzter Kurs {d['date'].iloc[-1].date()}", d


def technical_confirmation(prices):
    """Daily trend/momentum confirmation, returned only for validated prices."""
    if prices is None or len(prices) < 220:
        return None, "Technische Historie unzureichend"
    close = prices["close"].astype(float)
    last = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])
    momentum20 = float(close.pct_change(20).iloc[-1])
    if not np.isfinite([last, sma50, sma200, momentum20]).all():
        return None, "Technische Kennzahlen ungültig"
    if last > sma50 and sma50 > sma200 and momentum20 > 0:
        return 1, f"Bullish bestätigt: Kurs>SMA50>SMA200, 20T-Momentum {momentum20:.2%}"
    if last < sma50 and sma50 < sma200 and momentum20 < 0:
        return -1, f"Bearish bestätigt: Kurs<SMA50<SMA200, 20T-Momentum {momentum20:.2%}"
    return 0, f"Kein eindeutiger Trend: 20T-Momentum {momentum20:.2%}"


def combine_fx_signal(component_scores, component_valid, technical_score):
    """Score weights: macro 40, COT 25, seasonality 10. Technical confirms/blocks."""
    required = ("macro", "cot", "seasonality")
    missing = [name for name in required if not component_valid.get(name, False)]
    if missing or technical_score is None:
        return {"bias": "NEUTRAL", "score": None, "reason": "Unzureichende validierte Daten: " + ", ".join(missing + (["Technik"] if technical_score is None else [])), "signal_quality": "NICHT BEWERTBAR"}
    score = round((0.40 * component_scores["macro"] + 0.25 * component_scores["cot"] + 0.10 * component_scores["seasonality"]) / 0.75)
    # Technical analysis confirms or blocks; it does not add to the directional score.
    if score >= LONG_SHORT_THRESHOLD:
        bias = "LONG" if technical_score == 1 else "NEUTRAL"
        reason = "Technik bestätigt LONG" if technical_score == 1 else "LONG blockiert: Technik bestätigt nicht bullish"
    elif score <= -LONG_SHORT_THRESHOLD:
        bias = "SHORT" if technical_score == -1 else "NEUTRAL"
        reason = "Technik bestätigt SHORT" if technical_score == -1 else "SHORT blockiert: Technik bestätigt nicht bearish"
    else:
        bias, reason = "NEUTRAL", "Score innerhalb der Schwelle ±20"
    return {"bias": bias, "score": score, "reason": reason, "signal_quality": "MITTEL" if bias != "NEUTRAL" else "NIEDRIG"}


def quality_percent(valid_flags):
    if not valid_flags:
        return 0
    return round(100 * sum(bool(x) for x in valid_flags) / len(valid_flags))

st.title("⌁ MACRO / REGIME TERMINAL")
st.caption("Forex only · Makro · COT · Saisonalität · technische Bestätigung")
st.warning("Datenstatus: Ohne konfigurierte Datenquelle werden keine aktuellen Marktmeinungen behauptet. Historische Daten sind nicht automatisch Echtzeitdaten; Anbieter, Verzögerung und Lizenzbedingungen beachten.")

with st.sidebar:
    st.header("Einstellungen")
    page = st.radio("Modul", ["Übersicht", "FX Signal", "Saisonalität", "COT / Positioning", "NQ & ES", "Quant & Regression", "Datenquellen"])
    st.divider()
    try:
        saved_fred_key = st.secrets.get("FRED_API_KEY", "")
    except Exception:
        saved_fred_key = ""
    fred_key = st.text_input(
        "FRED API-Key (optional)", value=saved_fred_key, type="password",
        help="Hier eingeben oder sicher in Streamlit Secrets als FRED_API_KEY hinterlegen."
    )
    st.caption(f"Ansicht erstellt: {utc_now()}")
    st.caption("Build: FX Signal Engine v1.1 · Bias nur aus validierten Daten")

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
    st.write("Forex-Paare · relatives Makro beider Währungsräume · COT-Futures-Positionierung · Monats-Saisonalität · technische Bestätigung · Daten- und Signalqualität")
    st.markdown("#### Start-Checkliste")
    st.write("- [ ] FRED API-Key für Makro- und Zinsserien hinterlegen")
    st.write("- [ ] Historische Forex-Preise abrufen und Aktualität/Vollständigkeit prüfen")
    st.write("- [ ] CFTC-Kontrakte/Kategorien korrekt zuordnen")
    st.write("- [ ] Regeln und Schwellenwerte testen, bevor Signale produktiv genutzt werden")

elif page in ("FX Signal", "FX Macro"):
    st.subheader("Forex Bias Engine")
    st.caption("LONG/SHORT erst ab ±20 und nur, wenn Makro, COT, Saisonalität sowie technische Bestätigung validiert sind. Nicht verbundene Faktoren erzwingen NEUTRAL.")
    pair = st.selectbox("Forex-Paar", list(FX_PAIRS.keys()))
    pair_info = FX_PAIRS[pair]
    st.markdown("#### Datenvalidierung & Bias")
    if st.button("Echte Kursdaten laden und validieren", type="primary"):
        try:
            price_df = load_market_history(pair_info["symbol"], "2y")
            price_ok, price_message, validated_prices = validate_price_history(price_df)
            tech_score, tech_message = technical_confirmation(validated_prices) if price_ok else (None, "Technik blockiert: Kursdaten nicht validiert")
            # The current starter project does not yet contain validated, pair-relative macro
            # datasets or a verified CFTC contract/position mapping. Never infer these from a USD-only feed.
            component_valid = {"macro": False, "cot": False, "seasonality": False}
            component_scores = {}
            result = combine_fx_signal(component_scores, component_valid, tech_score)
            flags = [price_ok, component_valid["macro"], component_valid["cot"], component_valid["seasonality"], tech_score is not None]
            q_data = quality_percent(flags)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Bias", result["bias"])
            c2.metric("Gesamtscore", "—" if result["score"] is None else f"{result['score']:+d} / 100")
            c3.metric("Datenqualität", f"{q_data}%")
            c4.metric("Signalqualität", result["signal_quality"])
            st.info(result["reason"])
            st.write("**Technische Prüfung:**", tech_message)
            st.write("**Kursdaten:**", price_message)
            quality_rows = [
                {"Komponente": "FX-Kursdaten", "Status": "VALIDIERT" if price_ok else "UNGÜLTIG", "Einordnung": price_message},
                {"Komponente": "Relatives Makro beider Währungen", "Status": "FEHLT", "Einordnung": "Derzeit nur US-FRED-Serien angebunden; kein valider Vergleich beider Währungsräume."},
                {"Komponente": "COT", "Status": "FEHLT", "Einordnung": f"Kontrakt {pair_info['cot']} muss über Reporttyp, Contract und Positionsfelder verifiziert werden."},
                {"Komponente": "Saisonalität", "Status": "FEHLT", "Einordnung": "Historische Preise sind abrufbar, aber saisonale Stichprobe/Abdeckung wird noch nicht als validierter Signalinput freigegeben."},
                {"Komponente": "Technische Bestätigung", "Status": "VALIDIERT" if tech_score is not None else "FEHLT", "Einordnung": tech_message},
            ]
            st.dataframe(pd.DataFrame(quality_rows), use_container_width=True, hide_index=True)
            if price_ok:
                st.line_chart(validated_prices.set_index("date")["close"])
            st.warning("Fail-closed aktiv: Der Bias bleibt NEUTRAL, bis alle drei nichttechnischen Komponenten aus echten, korrekt zugeordneten und frischen Daten validiert sind. Eine vorhandene USD-FRED-Serie reicht für EUR/USD oder andere Paare nicht aus.")
        except Exception as exc:
            st.error(f"Kursabruf/Validierung fehlgeschlagen: {exc}")
            st.metric("Bias", "NEUTRAL")
            st.metric("Datenqualität", "0% / nicht validiert")
    else:
        st.info("Noch keine aktuelle Kursprüfung durchgeführt. Ohne erfolgreichen Datenabruf bleibt der Bias NEUTRAL.")
    st.divider()
    st.subheader("Makro-Datenlabor (USD, nicht allein signalberechtigt)")
    st.caption("Lädt verfügbare US-Makroserien aus FRED. Das ist noch kein vollständiger G10-Vergleich; andere Länder benötigen eigene Datenzuordnungen.")
    fred_series = {
        "FEDFUNDS": ("US Effective Federal Funds Rate", "% p.a."),
        "CPIAUCSL": ("US CPI Index", "Index"),
        "UNRATE": ("US Arbeitslosenquote", "%"),
        "DGS10": ("US Treasury 10Y", "% p.a."),
        "DGS2": ("US Treasury 2Y", "% p.a."),
        "T10YIE": ("US 10Y Breakeven Inflation", "% p.a."),
        "DTWEXBGS": ("US Dollar Index (breit, nominal)", "Index"),
    }
    if not fred_key:
        st.info("Trage links deinen FRED API-Key ein. Danach kannst du die US-Makroindikatoren laden.")
    selected = st.multiselect("Indikatoren", list(fred_series.keys()), default=["FEDFUNDS", "CPIAUCSL", "UNRATE", "DGS10", "DGS2"], format_func=lambda sid: f"{sid} — {fred_series[sid][0]}")
    if st.button("US-Makroindikatoren laden", type="primary"):
        if not fred_key:
            st.error("Bitte zuerst links einen FRED API-Key eintragen.")
        elif not selected:
            st.warning("Bitte mindestens einen Indikator auswählen.")
        else:
            summary, errors = [], []
            loaded_series = {}
            with st.spinner("Lade FRED-Daten…"):
                for sid in selected:
                    try:
                        series_df = get_fred_series(sid, fred_key)
                        loaded_series[sid] = series_df.copy()
                        if series_df.empty:
                            errors.append(f"{sid}: keine Beobachtungen zurückgegeben.")
                            continue
                        last = series_df.iloc[-1]
                        prev = series_df.iloc[-2] if len(series_df) > 1 else None
                        summary.append({"Serie": sid, "Indikator": fred_series[sid][0], "Letztes Datum": last["date"].date().isoformat(), "Letzter Wert": float(last["value"]), "Einheit": fred_series[sid][1], "Vorwert": float(prev["value"]) if prev is not None else None, "Beobachtungen": len(series_df)})
                    except Exception as exc:
                        errors.append(f"{sid}: {exc}")
            if summary:
                result = pd.DataFrame(summary)
                st.success(f"{len(summary)} von {len(selected)} Serien erfolgreich geladen.")
                st.dataframe(result, use_container_width=True, hide_index=True)
                chosen = st.selectbox("Serie im Verlauf anzeigen", [r["Serie"] for r in summary], format_func=lambda sid: f"{sid} — {fred_series[sid][0]}")
                try:
                    history = get_fred_series(chosen, fred_key)
                    st.line_chart(history.set_index("date")["value"])
                    st.caption(f"Quelle: FRED · Serie {chosen} · letzter verfügbarer Datenpunkt {history.iloc[-1]['date'].date().isoformat()}. Frequenz und Aktualisierung hängen von der Serie ab; keine garantierten Echtzeitdaten.")
                    st.dataframe(history.tail(12), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.error(f"Verlauf konnte nicht angezeigt werden: {exc}")
            if errors:
                st.warning("Einige Serien konnten nicht geladen werden: " + " | ".join(errors))

            st.info("Die geladenen US-Makroserien dienen derzeit nur der Dateninspektion. Sie erzeugen keinen Forex-Bias, da ein validierter Vergleich mit dem Gegenwährungsraum und Konsistenzchecks fehlen.")
    st.markdown("#### Status der G10-Abdeckung")
    coverage = pd.DataFrame([
        ["USD", "Teilweise verbunden", "US-Makroindikatoren oben über FRED ladbar"],
        ["EUR", "Nicht verbunden", "EZB-/Eurostat-Serien separat integrieren"],
        ["GBP", "Nicht verbunden", "BoE-/ONS-Serien separat integrieren"],
        ["JPY", "Nicht verbunden", "BoJ-/Japan-Statistikserien separat integrieren"],
        ["CHF", "Nicht verbunden", "SNB-/Schweizer Statistikserien separat integrieren"],
        ["CAD", "Nicht verbunden", "BoC-/Statistics Canada-Serien separat integrieren"],
        ["AUD", "Nicht verbunden", "RBA-/ABS-Serien separat integrieren"],
        ["NZD", "Nicht verbunden", "RBNZ-/Stats NZ-Serien separat integrieren"],
    ], columns=["CCY", "Status", "Hinweis"])
    st.dataframe(coverage, use_container_width=True, hide_index=True)

elif page == "Saisonalität":
    st.subheader("Monatliche Saisonalität")
    symbols = {name: info["symbol"] for name, info in FX_PAIRS.items()}
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
        ["FX-Kurse", "FX-Datenanbieter / Broker", "Aktualität, Historie und Lizenzbedingungen validieren"],
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
st.caption("Macro / Regime Terminal — Forex-only Signal Engine. NEUTRAL bei unzureichenden oder nicht validierten Daten. Keine Anlageberatung.")
