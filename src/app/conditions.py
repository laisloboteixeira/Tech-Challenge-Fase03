# src/app/conditions.py
from typing import Tuple, Optional
import duckdb
import pandas as pd
import altair as alt
import streamlit as st


# ------------------------------ utilidades ------------------------------ #
def decode_wmo(code) -> Tuple[str, str]:
    """Mapeia WMO weathercode -> (descrição PT-BR, emoji)."""
    try:
        code = int(code)
    except Exception:
        return ("Indefinido", "🌡️")
    m = {
        0: ("Céu limpo", "☀️"),
        1: ("Predomínio de sol", "🌤️"),
        2: ("Parcialmente nublado", "⛅"),
        3: ("Nublado", "☁️"),
        45: ("Névoa", "🌫️"), 48: ("Névoa gelada", "🌫️"),
        51: ("Garoa fraca", "🌦️"), 53: ("Garoa", "🌦️"), 55: ("Garoa forte", "🌧️"),
        56: ("Garoa gelada", "🌧️"), 57: ("Garoa gelada forte", "🌧️"),
        61: ("Chuva fraca", "🌧️"), 63: ("Chuva", "🌧️"), 65: ("Chuva forte", "🌧️"),
        66: ("Chuva congelante", "🌧️"), 67: ("Chuva congelante forte", "🌧️"),
        71: ("Neve fraca", "❄️"), 73: ("Neve", "❄️"), 75: ("Neve forte", "❄️"),
        77: ("Grãos de neve", "❄️"),
        80: ("Pancadas isoladas", "🌦️"), 81: ("Pancadas", "🌧️"), 82: ("Pancadas fortes", "🌧️"),
        85: ("Pancadas de neve", "❄️"), 86: ("Pancadas de neve fortes", "❄️"),
        95: ("Tempestade", "⛈️"),
        96: ("Tempestade com granizo", "⛈️"),
        99: ("Tempestade forte com granizo", "⛈️"),
    }
    return m.get(code, ("Indefinido", "🌡️"))


def heat_index_c(temp_c: Optional[float], rh: Optional[float]) -> Optional[float]:
    """Sensação térmica (heat index). Retorna °C ou None se não der pra calcular."""
    import math
    if temp_c is None or rh is None:
        return None
    if pd.isna(temp_c) or pd.isna(rh):
        return None
    # fórmula NOAA (em °F) e volta pra °C
    T = temp_c * 9 / 5 + 32
    R = rh
    HI = (
        -42.379 + 2.04901523 * T + 10.14333127 * R
        - 0.22475541 * T * R - 0.00683783 * T * T - 0.05481717 * R * R
        + 0.00122874 * T * T * R + 0.00085282 * T * R * R
        - 0.00000199 * T * T * R * R
    )
    if (R < 13) and (80 <= T <= 112):
        HI -= ((13 - R) / 4) * math.sqrt((17 - abs(T - 95)) / 17)
    if (R > 85) and (80 <= T <= 87):
        HI += ((R - 85) / 10) * ((87 - T) / 5)
    return (HI - 32) * 5 / 9


# ------------------------------- UI/consulta ---------------------------- #
def render_conditions(DB_PATH, latitude: float, longitude: float, tz: str):
    # compactar st.metric
    st.markdown(
        """
        <style>
        div[data-testid="stMetricValue"]{font-size:15px!important;line-height:1.2!important}
        div[data-testid="stMetricLabel"]{font-size:12px!important}
        </style>
        """,
        unsafe_allow_html=True,
    )

    lat = round(float(latitude), 4)
    lon = round(float(longitude), 4)

    # traz colunas necessárias (inclui umidade para sensação térmica)
    with duckdb.connect(DB_PATH.as_posix()) as con:
        df = con.execute(
            """
            SELECT
                ts,
                temperature_2m,
                relative_humidity_2m,
                weathercode,
                precipitation,
                precipitation_probability,
                cloudcover
            FROM raw.weather_hourly
            WHERE ROUND(latitude, 4) = ? AND ROUND(longitude, 4) = ?
            ORDER BY ts
            """,
            [lat, lon],
        ).df()

    if df.empty:
        st.info("Sem registros ainda — use os botões de coleta/backfill.")
        return

    # garantir tipos
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    for c in [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "precipitation_probability",
        "cloudcover",
        "weathercode",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")

    # prob. de chuva com fallback (quando API não trouxer)
    rain_codes = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    df["pop"] = df.get("precipitation_probability")
    df.loc[df["pop"].isna() & df["weathercode"].isin(list(rain_codes)), "pop"] = 70.0
    df.loc[df["pop"].isna() & (df["precipitation"] > 0), "pop"] = 50.0
    df["pop"] = df["pop"].clip(0, 100)

    now_utc = pd.Timestamp.now(tz="UTC")
    now_row = df[df["ts"] <= now_utc].tail(1)
    next_row = df[df["ts"] > now_utc].head(1)

    # métricas
    col1, col2, col3, col4 = st.columns([1.2, 1, 1.2, 1.2])

    if not now_row.empty:
        rnow = now_row.iloc[0]
        desc_pt, emoji = decode_wmo(rnow["weathercode"])
        prob_now = rnow["pop"]
        precip_now = rnow["precipitation"]
        feels = heat_index_c(rnow["temperature_2m"], rnow["relative_humidity_2m"])

        col1.metric("Agora", f"{emoji} {desc_pt}")
        col2.metric("Prob. de chuva", "—" if pd.isna(prob_now) else f"{prob_now:.0f}%")
        col3.metric("Precipitação", "—" if pd.isna(precip_now) else f"{precip_now:.1f} mm")
        col4.metric("Sensação", "—" if (feels is None or pd.isna(feels)) else f"{feels:.1f} °C")

    if not next_row.empty:
        rnx = next_row.iloc[0]
        desc_pt, emoji = decode_wmo(rnx["weathercode"])
        prob_next = rnx["pop"]
        prob_next_str = "—" if pd.isna(prob_next) else f"{prob_next:.0f}%"
        st.caption(f"**Próxima hora:** {emoji} {desc_pt} — Prob. {prob_next_str}")

    # mini timeline (próximas 6h)
    nxt6 = df[(df["ts"] > now_utc) & (df["ts"] <= now_utc + pd.Timedelta(hours=6))].head(6)
    if not nxt6.empty:
        st.caption("**Próximas 6h**")
        cols = st.columns(len(nxt6))
        for i, (_, rr) in enumerate(nxt6.reset_index(drop=True).iterrows()):
            dpt, em = decode_wmo(rr["weathercode"])
            t_local = rr["ts"].tz_convert(tz).strftime("%Hh")
            p = rr.get("pop", None)
            ptxt = "" if pd.isna(p) else f"<br/><small>{p:.0f}%</small>"
            with cols[i]:
                st.markdown(
                    f"<div style='text-align:center'>{em}<br/><small>{t_local}</small>{ptxt}</div>",
                    unsafe_allow_html=True,
                )

    # gráfico de prob. de chuva (barras) com marcador do "agora"
    df_plot = df.assign(local=df["ts"].dt.tz_convert(tz))
    df_plot["pop"] = df_plot["pop"].fillna(0)

    bars = (
        alt.Chart(df_plot)
        .mark_bar()
        .encode(
            x="local:T",
            y=alt.Y("pop:Q", title="Prob. de chuva (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("local:T", title="Hora"),
                alt.Tooltip("pop:Q", title="Prob (%)", format=".0f"),
            ],
        )
        .properties(height=160)
    )

    now_rule = alt.Chart(pd.DataFrame({"local": [pd.Timestamp.now(tz=tz)]})).mark_rule(
        strokeDash=[4, 4]
    ).encode(x="local:T")

    st.altair_chart(bars + now_rule, use_container_width=True)

    # alertas simples
    if (pd.to_numeric(df["weathercode"], errors="coerce") >= 95).any():
        st.warning("⚠️ Possibilidade de **tempestade** nas próximas horas.")
    if pd.to_numeric(df["temperature_2m"], errors="coerce").max() >= 37:
        st.warning("🥵 **Onda de calor** (≥ 37 °C) detectada.")
