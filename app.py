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
