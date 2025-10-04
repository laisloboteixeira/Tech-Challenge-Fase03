# src/ingestion/api.py
# API para coletar clima horário (Open-Meteo) e gravar em DuckDB.
# - /collect: últimas horas (forecast) -> filtra FUTURO
# - /backfill: histórico por intervalo (start_date/end_date) ou por 'days'
# - Dedup por (ts, latitude, longitude)
# - Lat/Lon normalizados (4 casas)

from pathlib import Path
from datetime import date, timedelta
from typing import Optional

import duckdb
import pandas as pd
import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
DB_PATH = Path("data") / "rt_weather.duckdb"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",   # pode vir como 'relativehumidity_2m'
    "precipitation",
    "wind_speed_10m",         # pode vir como 'windspeed_10m'
    "weathercode",
    "precipitation_probability",
    "cloudcover",
]

# ---------------------------------------------------------------------
# DuckDB: criar tabela se não existir (10 colunas)
# ---------------------------------------------------------------------
def ensure_table() -> None:
    con = duckdb.connect(DB_PATH.as_posix())
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.weather_hourly (
            ts TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            temperature_2m DOUBLE,
            relative_humidity_2m DOUBLE,
            precipitation DOUBLE,
            wind_speed_10m DOUBLE,
            weathercode SMALLINT,
            precipitation_probability DOUBLE,
            cloudcover DOUBLE
        );
        """
    )
    # Migração idempotente (ignora se já existir)
    for col, typ in [
        ("weathercode", "SMALLINT"),
        ("precipitation_probability", "DOUBLE"),
        ("cloudcover", "DOUBLE"),
    ]:
        try:
            con.execute(f"ALTER TABLE raw.weather_hourly ADD COLUMN {col} {typ};")
        except Exception:
            pass
    con.close()

ensure_table()

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _json_to_df(payload: dict, lat: float, lon: float) -> pd.DataFrame:
    """Converte o JSON da Open-Meteo em DataFrame; ts fica naive em UTC."""
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    n = len(times)

    df = pd.DataFrame({"ts": pd.to_datetime(times, utc=True)})

    # alguns campos têm nome alternativo na API
    def pick(key: str):
        if key == "relative_humidity_2m":
            return hourly.get("relative_humidity_2m") or hourly.get("relativehumidity_2m")
        if key == "wind_speed_10m":
            return hourly.get("wind_speed_10m") or hourly.get("windspeed_10m")
        return hourly.get(key)

    for k in HOURLY_VARS:
        vals = pick(k)
        if vals is None or len(vals) != n:
            vals = [None] * n
        df[k] = vals

    df["latitude"] = round(lat, 4)
    df["longitude"] = round(lon, 4)

    # deixa ts como naive em UTC (compatível com TIMESTAMP do DuckDB)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)

    # ordem final: ts, lat/lon, depois variáveis horárias
    return df[["ts", "latitude", "longitude"] + HOURLY_VARS]


def _insert_new_rows(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Conta e insere apenas as linhas novas usando SELECT … EXCEPT …"""
    if df.empty:
        return 0
    con.register("df", df)

    # Conta quantas serão inseridas
    n = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT
              ts, latitude, longitude,
              temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m,
              weathercode, precipitation_probability, cloudcover
            FROM df
            EXCEPT
            SELECT
              ts, latitude, longitude,
              temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m,
              weathercode, precipitation_probability, cloudcover
            FROM raw.weather_hourly
        ) t
    """).fetchone()[0]

    # Faz o INSERT
    con.execute("""
        INSERT INTO raw.weather_hourly (
          ts, latitude, longitude,
          temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m,
          weathercode, precipitation_probability, cloudcover
        )
        SELECT
          ts, latitude, longitude,
          temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m,
          weathercode, precipitation_probability, cloudcover
        FROM df
        EXCEPT
        SELECT
          ts, latitude, longitude,
          temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m,
          weathercode, precipitation_probability, cloudcover
        FROM raw.weather_hourly;
    """)

    return int(n)

# ---------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------
app = FastAPI(
    title="Tech Challenge Fase 3 – Weather API",
    description="Coleta de clima horário (Open-Meteo) + persistência em DuckDB",
    version="1.2.0",
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/collect")
def collect(
    latitude: float = Query(-23.55),
    longitude: float = Query(-46.63),
    past_hours: int = Query(6, ge=1, le=168),
):
    try:
        ensure_table()
        lat, lon = round(latitude, 4), round(longitude, 4)

        hourly_list = ",".join(HOURLY_VARS)
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly={hourly_list}"
            f"&past_hours={past_hours}"
            f"&forecast_hours=48"
            f"&timezone=UTC"
        )
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        df = _json_to_df(r.json(), lat, lon)

        # filtra FUTURO de forma tz-aware (evita erro de comparação)
        ts_aware = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df = df[ts_aware <= pd.Timestamp.now(tz="UTC")]

        con = duckdb.connect(DB_PATH.as_posix())
        inserted = _insert_new_rows(con, df)
        first_ts = df["ts"].min().isoformat() if not df.empty else None
        last_ts  = df["ts"].max().isoformat() if not df.empty else None
        con.close()

        return {
            "inserted_rows": inserted,
            "rows_returned": int(len(df)),
            "lat": lat,
            "lon": lon,
            "timezone": "UTC",
            "first_ts_utc": first_ts,
            "last_ts_utc": last_ts,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/backfill")
def backfill(
    latitude: float = Query(-23.55),
    longitude: float = Query(-46.63),
    days: int = Query(30, ge=1, le=180),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    try:
        ensure_table()
        lat, lon = round(latitude, 4), round(longitude, 4)

        if not start_date or not end_date:
            end = date.today()
            start = end - timedelta(days=days)
            s, e = start.isoformat(), end.isoformat()
        else:
            s, e = start_date, end_date

        hourly_list = ",".join(HOURLY_VARS)
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}"
            f"&start_date={s}&end_date={e}"
            f"&hourly={hourly_list}"
            f"&timezone=UTC"
        )
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = _json_to_df(r.json(), lat, lon)

        con = duckdb.connect(DB_PATH.as_posix())
        inserted = _insert_new_rows(con, df)
        first_ts = df["ts"].min().isoformat() if not df.empty else None
        last_ts  = df["ts"].max().isoformat() if not df.empty else None
        con.close()

        return {
            "inserted_rows": inserted,
            "rows_returned": int(len(df)),
            "lat": lat,
            "lon": lon,
            "first_ts_utc": first_ts,
            "last_ts_utc": last_ts,
            "range_used": {"start_date": s, "end_date": e},
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
