from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "rt_weather.duckdb"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(DB_PATH.as_posix())
con.execute("CREATE SCHEMA IF NOT EXISTS raw;")

# cria a tabela caso não exista (baseline)
con.execute("""
CREATE TABLE IF NOT EXISTS raw.weather_hourly (
    ts TIMESTAMP,
    latitude DOUBLE,
    longitude DOUBLE,
    temperature_2m DOUBLE,
    relative_humidity_2m DOUBLE,
    precipitation DOUBLE,
    wind_speed_10m DOUBLE
);
""")

# adiciona colunas novas se faltarem 
for col, typ in [
    ("weathercode", "SMALLINT"),
    ("precipitation_probability", "DOUBLE"),
    ("cloudcover", "DOUBLE"),
]:
    try:
        con.execute(f"ALTER TABLE raw.weather_hourly ADD COLUMN {col} {typ};")
    except Exception:
        pass

print(con.execute("PRAGMA table_info('raw.weather_hourly')").df())
con.close()
print(f"✅ Migração concluída em: {DB_PATH}")
