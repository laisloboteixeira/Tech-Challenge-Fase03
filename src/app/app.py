# src/app/app.py
# App Streamlit: histórico + previsão da PRÓXIMA hora (t+1h)
# - Seleção de cidade ou coordenadas
# - Hora local do lugar + último registro local + Δh
# - Coleta via API (collect/backfill)
# - Limpeza SOMENTE de dados brutos (raw.weather_hourly): por cidade ou geral
# - Gráfico no fuso da cidade (dedup por hora + gaps explícitos)
# - Inferência alinhada às features do treino (feature_cols.json)
# - Mantém: render_conditions (sua feature extra)

# --- garantir que a raiz do projeto esteja no sys.path (para importar src/*) ---
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# ------------------------------------------------------------------------------
# sua feature extra (mantido)
try:
    from src.app.conditions import render_conditions
except Exception:
    render_conditions = None  # caso o arquivo não exista, o app continua

import json
import requests
import duckdb
import joblib
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from src.processing.prepare_data import make_features  # MESMAS features do treino

# --------------------------- 
# Caminhos e configs
# ---------------------------
DB_PATH = ROOT / "data" / "rt_weather.duckdb"
MODEL_PATH = ROOT / "models" / "model_rf_temp_next_hour.pkl"
FEATURES_PATH = ROOT / "models" / "feature_cols.json"
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="RT Weather – Next Hour Temp", layout="centered")
st.title("🌦️ Previsão de Temperatura (Próxima Hora)")

# ---------------------------
# Utilitários
# ---------------------------
def get_timezone_for(lat: float, lon: float) -> str:
    """Descobre o fuso da localidade consultando a Open-Meteo (não grava no DB)."""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("timezone", "UTC")
    except Exception:
        return "UTC"


def get_last_ts_utc_for(lat: float, lon: float):
    """MAX(ts) para a cidade atual (UTC, naive)."""
    if not DB_PATH.exists():
        return None
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        return con.execute(
            """
            SELECT MAX(ts)
            FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4)
              AND round(longitude,4)=round(?,4)
            """,
            [lat, lon],
        ).fetchone()[0]
    except Exception:
        return None
    finally:
        con.close()


def delete_raw_city(lat: float, lon: float) -> int:
    """Remove SOMENTE linhas da cidade atual."""
    if not DB_PATH.exists():
        return 0
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        n = con.execute(
            """
            SELECT COUNT(*) FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4)
              AND round(longitude,4)=round(?,4)
            """,
            [lat, lon],
        ).fetchone()[0]
        con.execute(
            """
            DELETE FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4)
              AND round(longitude,4)=round(?,4)
            """,
            [lat, lon],
        )
        return int(n)
    except Exception:
        return 0
    finally:
        con.close()


def delete_raw_all() -> int:
    """Remove TODAS as linhas da tabela bruta (não mexe em refined/modelos)."""
    if not DB_PATH.exists():
        return 0
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        n = con.execute("SELECT COUNT(*) FROM raw.weather_hourly").fetchone()[0]
        con.execute("DELETE FROM raw.weather_hourly")
        return int(n)
    except Exception:
        return 0
    finally:
        con.close()


def load_city_raw(lat: float, lon: float):
    """
    Lê APENAS a cidade selecionada, ordenada, e devolve:
    - df_agg: 1 ponto por hora (média) em UTC tz-aware ('ts_utc') + colunas climáticas
              + 'ts' (UTC naive) para compatibilidade com make_features
    - df_local: com 'ts_local' no fuso detectado, contínuo de 1h (gaps = NaN)
    - tz: timezone da cidade
    """
    if not DB_PATH.exists():
        return pd.DataFrame(), pd.DataFrame(), "UTC"

    tz = get_timezone_for(lat, lon)
    now_utc = pd.Timestamp.now("UTC").floor("H")

    con = duckdb.connect(DB_PATH.as_posix())
    df = con.execute(
        """
        SELECT *
        FROM raw.weather_hourly
        WHERE round(latitude,4)=round(?,4)
          AND round(longitude,4)=round(?,4)
        ORDER BY ts
        """,
        [lat, lon],
    ).df()
    con.close()

    if df.empty:
        return df, df, tz  # vazio

    # 1) normaliza ts em UTC (tz-aware) + uma linha por HORA (média) e remove futuro
    df["ts_utc"] = pd.to_datetime(df["ts"]).dt.tz_localize("UTC").dt.floor("H")
    df_agg = (
        df.groupby("ts_utc", as_index=False)
        .agg(
            {
                "temperature_2m": "mean",
                "relative_humidity_2m": "mean",
                "precipitation": "mean",
                "wind_speed_10m": "mean",
                "latitude": "first",
                "longitude": "first",
            }
        )
    )
    df_agg = df_agg[df_agg["ts_utc"] <= now_utc]

    # 2) versão local para gráficos/tabela (index contínuo H)
    df_local = df_agg.copy()
    df_local["ts_local"] = df_local["ts_utc"].dt.tz_convert(tz)
    df_local = (
        df_local.set_index("ts_local")
        .asfreq("H")  # cria a grade horária, gaps ficam como NaN -> o gráfico "quebra"
        .sort_index()
    )

    # 3) coluna 'ts' naive UTC para features (compatível com make_features)
    df_agg["ts"] = df_agg["ts_utc"].dt.tz_convert("UTC").dt.tz_localize(None)

    return df_agg, df_local, tz


# ---------------------------
# Seleção do local
# ---------------------------
st.subheader("Local")

CITIES = {
    "São Paulo, BR": (-23.55, -46.63),
    "Rio de Janeiro, BR": (-22.9000, -43.2000),
    "Belo Horizonte, BR": (-19.9167, -43.9345),
    "Curitiba, BR": (-25.4284, -49.2733),
    "Porto Alegre, BR": (-30.0331, -51.2300),
    "Lisboa, PT": (38.7223, -9.1393),
    "Porto, PT": (41.1579, -8.6291),
    "Madrid, ES": (40.4168, -3.7038),
    "Londres, UK": (51.5074, -0.1278),
    "Berlim, DE": (52.5244, 13.4105),
    "Nova York, US": (40.7128, -74.0060),
    "Tóquio, JP": (35.6762, 139.6503),
    "Sydney, AU": (-33.8688, 151.2093),
}

modo = st.radio(
    "Como escolher o lugar?",
    ["Lista de cidades", "Coordenadas manuais"],
    horizontal=True,
)

if modo == "Lista de cidades":
    cidade = st.selectbox("Cidade", list(CITIES.keys()), index=0)
    lat, lon = CITIES[cidade]
    st.caption(f"Lat/Lon selecionados: {lat:.4f}, {lon:.4f}")
else:
    col1, col2 = st.columns(2)
    lat = col1.number_input("Latitude", value=-23.55, step=0.01, format="%.4f")
    lon = col2.number_input("Longitude", value=-46.63, step=0.01, format="%.4f")

# ---------------------------
# Barra lateral: Coleta + Relógio local + Limpeza de dados brutos
# ---------------------------
with st.sidebar:
    st.header("Coleta (API FastAPI)")
    if st.button("🔄 Coletar agora (últimas 6h)"):
        try:
            r = requests.get(
                f"{API_BASE}/collect",
                params={"latitude": lat, "longitude": lon, "past_hours": 6},
                timeout=30,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

    if st.button("📦 Backfill (últimos 30 dias)"):
        try:
            r = requests.post(
                f"{API_BASE}/backfill",
                params={"latitude": lat, "longitude": lon, "days": 30},
                timeout=120,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("🕒 Hora local & status")
    tz_sidebar = get_timezone_for(lat, lon)
    now_local = pd.Timestamp.now(tz_sidebar).floor("H")
    last_utc_city = get_last_ts_utc_for(lat, lon)
    if last_utc_city is not None:
        last_local = pd.Timestamp(last_utc_city, tz="UTC").tz_convert(tz_sidebar)
        delta_h = (now_local - last_local) / pd.Timedelta(hours=1)
        st.write(f"**Timezone:** {tz_sidebar}")
        st.write(f"**Agora (local):** {now_local}")
        st.write(f"**Último registro (local):** {last_local}")
        st.write(f"**Δ horas (atraso):** {delta_h:.1f} h")

        # sua seção extra (se existir)
        if render_conditions is not None:
            try:
                render_conditions(DB_PATH=DB_PATH, latitude=lat, longitude=lon, tz=tz_sidebar)
            except Exception as e:
                st.info(f"(conditions) {e}")
    else:
        st.info(f"Timezone: {tz_sidebar}\n\nSem registros ainda — faça o backfill/coleta.")

    st.divider()
    st.subheader("🧹 Limpar DADOS BRUTOS (raw)")
    st.caption("Remove apenas linhas de `raw.weather_hourly`. Não mexe em features/modelos.")

    col_a, col_b = st.columns(2)
    with col_a:
        confirm_city = st.checkbox("Confirmo (cidade atual)")
        if st.button("Apagar dados brutos\n(desta cidade)", disabled=not confirm_city):
            n = delete_raw_city(lat, lon)
            st.success(f"Removidas {n} linhas desta cidade.")
            st.experimental_rerun()
    with col_b:
        confirm_all = st.checkbox("Confirmo (todos os locais)")
        if st.button("Apagar dados brutos\n(todos os locais)", disabled=not confirm_all):
            n = delete_raw_all()
            st.success(f"Removidas {n} linhas de todos os locais.")
            st.experimental_rerun()

# ---------------------------
# Carregar dados da cidade
# ---------------------------
if not DB_PATH.exists():
    st.warning("Banco DuckDB não encontrado. Rode a API /backfill ou /collect primeiro.")
    st.stop()

df_agg, df_local, tz = load_city_raw(lat, lon)
if df_agg.empty:
    st.warning("Sem dados para esta cidade. Faça backfill/coleta.")
    st.stop()

# ---------------------------
# Gráfico principal (últimas 48h) — sem serrilhado e com gaps visíveis
# ---------------------------
st.write(f"Fuso da cidade: **{tz}**")
st.line_chart(df_local["temperature_2m"].tail(48))

# ---------------------------
# Carregar modelo e lista de features do treino
# ---------------------------
if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
    st.error(
        "Modelo/feature_cols não encontrados. Rode o treino primeiro "
        "(prepare_data.py e training/train.py)."
    )
    st.stop()

model = joblib.load(MODEL_PATH)
with open(FEATURES_PATH, "r", encoding="utf-8") as f:
    feature_cols = json.load(f)

# ---------------------------
# Gerar features atuais e ALINHAR ao conjunto do treino
# ---------------------------
# Para features, usamos df_agg (1/h em UTC) com coluna 'ts' (naive/UTC)
feat = make_features(df_agg.copy())
if len(feat) == 0:
    st.warning("Ainda não há features suficientes (rode mais coletas ou o backfill).")
    st.stop()

X = feat.drop(columns=["temp_t_plus_1h", "ts"], errors="ignore")

# adiciona colunas faltantes com zero e ordena exatamente como no treino
for c in feature_cols:
    if c not in X.columns:
        X[c] = 0
X = X[feature_cols]

# ---------------------------
# Previsão da próxima hora
# ---------------------------
x_last = X.iloc[[-1]]
y_hat = model.predict(x_last)[0]

st.subheader("🔮 Previsão (próxima hora)")
st.metric("Temperatura prevista", f"{y_hat:.2f} °C")

# gráfico com ponto previsto (+1h) no fuso local
fig, ax = plt.subplots()
hist = df_local["temperature_2m"].tail(24)
hist.plot(ax=ax)
if not hist.index.empty:
    ax.scatter([hist.index[-1] + pd.Timedelta(hours=1)], [y_hat], marker="x")
ax.set_title("Últimas 24h (local) + ponto previsto (+1h)")
ax.set_ylabel("ºC")
st.pyplot(fig)

# ---------------------------
# Tabela exploratória + download
# ---------------------------
with st.expander("🔎 Ver dados (tabela)"):
    st.caption(f"Fuso da cidade: **{tz}**")

    if "n_hours" not in st.session_state:
        st.session_state.n_hours = 168
    st.markdown(f"Mostrar últimas **{st.session_state.n_hours}** horas")
    st.session_state.n_hours = st.slider(
        label="", min_value=24, max_value=1000, value=st.session_state.n_hours, step=24,
        label_visibility="collapsed",
    )
    n = st.session_state.n_hours

    last_lat = df_agg["latitude"].round(4).iloc[-1]
    last_lon = df_agg["longitude"].round(4).iloc[-1]
    df_view = (
        df_local[["temperature_2m"]]
        .tail(n)
        .reset_index()
        .assign(latitude=last_lat, longitude=last_lon)
        [["ts_local", "latitude", "longitude", "temperature_2m"]]
    )

    st.dataframe(df_view, use_container_width=True, height=350)
    st.write("Total de linhas no banco (cidade):", len(df_local))

    csv = df_view.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (recorte mostrado)",
        data=csv,
        file_name=f"weather_last_{n}_hours_{last_lat:.4f}_{last_lon:.4f}.csv",
        mime="text/csv",
    )
