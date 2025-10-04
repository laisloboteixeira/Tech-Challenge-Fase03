# Tech Challenge – Fase 3 (FIAP)
## Previsão de Temperatura **e Condições** em Tempo *Quase* Real (Open-Meteo + FastAPI + DuckDB + Streamlit)

Projeto completo para **coletar dados horários de clima**, armazenar em **DuckDB**, (opcional) **treinar um modelo de ML** e disponibilizar um **dashboard** (Streamlit).  
Agora incluindo **condições do tempo** (WMO `weathercode`), **probabilidade de chuva**, **cobertura de nuvens**, **sensação térmica**, **timeline das próximas 6h** e **gráfico de probabilidade** com marcador do “agora”.

---

## 🔗 Sumário
- [Visão geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Pré-requisitos](#pré-requisitos)
- [Setup rápido](#setup-rápido)
- [Como rodar](#como-rodar)
  - [1) Subir a API (FastAPI)](#1-subir-a-api-fastapi)
  - [2) Trazer dados (Backfill / Collect)](#2-trazer-dados-backfill--collect)
  - [3) Preparar features (ML opcional)](#3-preparar-features-ml-opcional)
  - [4) Treinar o modelo (ML opcional)](#4-treinar-o-modelo-ml-opcional)
  - [5) Rodar o app (Streamlit)](#5-rodar-o-app-streamlit)
- [Endpoints da API](#endpoints-da-api)
- [Esquema do banco (DuckDB)](#esquema-do-banco-duckdb)
- [Geração de features & modelo (ML)](#geração-de-features--modelo-ml)
- [Dashboard / App (UI)](#dashboard--app-ui)
- [Utilitários](#utilitários)
- [Resolução de problemas](#resolução-de-problemas)
- [Critérios do Tech Challenge](#critérios-do-tech-challenge)
- [Licença](#licença)

---

## Visão geral
- **Coleta**: via **FastAPI** usando **Open-Meteo** (previsão e histórico).
- **Armazenamento**: **DuckDB** em `data/rt_weather.duckdb` (tabela `raw.weather_hourly`).
- **Processamento (ML opcional)**: `src/processing/prepare_data.py` gera *features* (Parquet).
- **Modelagem (ML opcional)**: `src/training/train.py` treina o modelo e salva artefatos.
- **Aplicação**: `src/app/app.py` (Streamlit) para:
  - selecionar cidade/coords e acionar **coleta/backfill** pela API;
  - visualizar **condições atuais** (emoji + descrição), **próxima hora**, **próximas 6h**;
  - ver **gráfico de probabilidade de chuva** (0–100%) em **barras** com marcador do “agora”;
  - (opcional) **prever a próxima hora** com o modelo treinado.

> 🔎 **Dedupe inteligente**: inserimos só linhas **novas** via `SELECT … EXCEPT …` no DuckDB.  
> ⏱️ **Timezone**: salvamos `ts` em **UTC (naive)**; comparações no app são **tz-aware**.

---

## Arquitetura
```
Open-Meteo (forecast/archive)
           │
           ▼
FastAPI (/collect, /backfill) ───► DuckDB (raw.weather_hourly)
           │                              │
           │                              └─► Parquet (features)  [prepare_data.py]
           │
           └────────► Streamlit (app.py) ◄─────────┐
                      • condições “agora”/“próxima hora”   │
                      • próximas 6h (emojis)               ├─ (opcional) usa modelo treinado
                      • gráfico prob. de chuva (0–100%)    │
                      • exportações                         ┘
```

---

## Estrutura do repositório
```
.
├── data/
│   ├── refined/                     # features .parquet (gerado)
│   └── rt_weather.duckdb            # banco DuckDB (gerado)
├── models/                          # modelos/artefatos (gerados)
│   ├── model.pkl
│   └── feature_cols.json
├── scripts/
│   └── migrate_duckdb.py            # migração de schema (opcional)
├── src/
│   ├── ingestion/
│   │   └── api.py                   # FastAPI (coleta/backfill + persistência)
│   ├── processing/
│   │   └── prepare_data.py          # gera features a partir do DuckDB
│   ├── training/
│   │   └── train.py                 # treina modelo e salva artefatos
│   └── app/
│       ├── app.py                   # dashboard Streamlit
│       └── conditions.py            # seção de condições (UI)
├── requirements.txt
└── README.md
```
> `data/rt_weather.duckdb` e `models/*` não devem ser versionados (veja `.gitignore`).

---

## Pré-requisitos
- **Python 3.11+** (Windows 11 recomendado; funciona em Linux/macOS)
- Pip
- Git

---

## Setup rápido
### Windows (PowerShell)
```powershell
git clone <SEU_REPO_AQUI>.git
cd <SEU_REPO_AQUI>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# se precisar complementar:
pip install streamlit fastapi uvicorn duckdb pandas requests altair
```

### Linux/macOS (bash)
```bash
git clone <SEU_REPO_AQUI>.git
cd <SEU_REPO_AQUI>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Como rodar

### 1) Subir a API (FastAPI)
```powershell
uvicorn src.ingestion.api:app --reload --host 127.0.0.1 --port 8000
```
Teste rápido:
```powershell
Invoke-WebRequest http://127.0.0.1:8000/health | Select-Object -ExpandProperty Content
# -> {"status":"ok"}
```

### 2) Trazer dados (Backfill / Collect)
Com a API ativa, em outro terminal:

**Backfill 30 dias (São Paulo)**
```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/backfill?latitude=-23.55&longitude=-46.63&days=30"
```

**Backfill por intervalo (um dia específico)**
```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/backfill?latitude=-23.55&longitude=-46.63&start_date=2025-09-16&end_date=2025-09-16"
```

**Coletar últimas 6h (forecast)**
```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/collect?latitude=-23.55&longitude=-46.63&past_hours=6"
```

> A API grava em `raw.weather_hourly` e **deduplica** por `(ts, latitude, longitude)`.  
> `ts` é salvo em **UTC (naive)**; o app converte para hora local.

### 3) Preparar features (ML opcional)
```powershell
$env:PYTHONPATH = (Get-Location)   # garante imports "src.*"
python -m src.processing.prepare_data
```
Gera `data/refined/weather_features.parquet`.

### 4) Treinar o modelo (ML opcional)
```powershell
python -m src.training.train
```
Salva (por padrão):
```
models/model.pkl
models/feature_cols.json
```
> Se seu `train.py` salvar com outro nome/caminho, ajuste os paths no `app.py`.

### 5) Rodar o app (Streamlit)
```powershell
streamlit run src/app/app.py
```
No app você pode:
- selecionar cidade/coords;
- acionar **Coletar** (últimas 6h) e **Backfill** (ex.: 30 dias);
- visualizar **condições agora**, **próxima hora** e **próximas 6h** (emojis/percentuais);
- ver **gráfico** de prob. de chuva (0–100%) com marcador do “agora”;
- (opcional) exibir o card de **previsão por ML** quando `models/model.pkl` e `models/feature_cols.json` existirem.

---

## Endpoints da API
**Base**: `http://127.0.0.1:8000` — **Swagger**: `http://127.0.0.1:8000/docs`

### `GET /health`
Retorna status da API.

### `GET /collect?latitude={lat}&longitude={lon}&past_hours={1..168}`
Coleta horas recentes (forecast), **filtra futuro** e grava no DuckDB.

### `POST /backfill?latitude={lat}&longitude={lon}&days={1..180}`
Histórico dos últimos N dias.

### `POST /backfill?latitude={lat}&longitude={lon}&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
Backfill com intervalo explícito.

**Resposta típica**
```json
{
  "inserted_rows": 144,
  "rows_returned": 144,
  "lat": -23.55,
  "lon": -46.63,
  "timezone": "UTC",
  "first_ts_utc": "2025-09-15T00:00:00",
  "last_ts_utc":  "2025-09-16T23:00:00",
  "range_used": {"start_date":"2025-09-15","end_date":"2025-09-16"}
}
```

---

## Esquema do banco (DuckDB)
Tabela `raw.weather_hourly`:
| coluna                      | tipo       | descrição                                   |
|----------------------------|------------|---------------------------------------------|
| ts                         | TIMESTAMP  | hora **UTC (naive)**                        |
| latitude                   | DOUBLE     | lat normalizada (4 casas)                   |
| longitude                  | DOUBLE     | lon normalizada (4 casas)                   |
| temperature_2m             | DOUBLE     | temperatura (°C)                            |
| relative_humidity_2m       | DOUBLE     | umidade relativa (%)                        |
| precipitation              | DOUBLE     | precipitação (mm)                           |
| wind_speed_10m             | DOUBLE     | velocidade do vento (km/h)                  |
| weathercode                | SMALLINT   | código WMO (condição)                       |
| precipitation_probability  | DOUBLE     | probabilidade de precipitação (%)           |
| cloudcover                 | DOUBLE     | cobertura de nuvens (%)                     |

- Inserção só de **linhas novas** com `SELECT … EXCEPT …`.
- `ts` salvo em **UTC (naive)**; comparações no app são **tz-aware**.

---

## Geração de features & modelo (ML)
**`src/processing/prepare_data.py`** (exemplos):
- *lags* (`temp_lag_1h`, `temp_lag_24h`), recursos cíclicos (`hour_sin`, `hour_cos`), médias móveis, etc.

**`src/training/train.py`**:
- split temporal train/test, métrica **MAE/RMSE**, baseline vs. modelo,
- salva **`models/model.pkl`** e **`models/feature_cols.json`**.

> O card de ML no app só aparece quando os artefatos existem; caso contrário o card é ocultado (ou exibido com aviso, dependendo do seu `app.py`).

---

## Dashboard / App (UI)
- **Condições agora**: emoji + descrição (`weathercode`), **prob. de chuva**, **precipitação**, **sensação térmica**.
- **Próxima hora** e **próximas 6h**: timeline compacta com emojis e percentuais.
- **Gráfico**: probabilidade de chuva (0–100%) em **barras** com **marcador do “agora”**.
- **Fallback de probabilidade**: quando `precipitation_probability` vier vazia (comum no backfill), usamos heurística simples (ex.: códigos de chuva → ~70%, precipitação>0 → ~50%).

---

## Utilitários
- `scripts/migrate_duckdb.py`: adiciona colunas novas ao schema existente (idempotente).  
  Alternativa rápida: apagar `data/rt_weather.duckdb` e reexecutar backfill/coleta.

---

## Resolução de problemas
- **Conexão recusada no app** → Suba a API antes (`uvicorn …`) e confirme `API_BASE` no `app.py`.
- **`Invalid comparison between dtype=datetime64[ns] and Timestamp`** → app atual compara datas **tz-aware**; atualize para a versão deste repo.
- **DuckDB: `changes()` não existe** → usamos contagem via `SELECT COUNT(*) FROM (SELECT … EXCEPT …)` antes do `INSERT`.
- **`No module named src` ao rodar scripts** → na raiz, exporte:  
  `PowerShell: $env:PYTHONPATH = (Get-Location)`  
  `bash: export PYTHONPATH=$(pwd)`
- **`weather_features.parquet` não encontrado** → rode `python -m src.processing.prepare_data` antes do treino.
- **Schema antigo** (faltando `weathercode`/`precipitation_probability`/`cloudcover`) → execute `scripts/migrate_duckdb.py` ou apague `data/rt_weather.duckdb` e refaça o backfill.

---

## Critérios do Tech Challenge
✔️ **Problema**: série temporal (prever temperatura próxima hora) + visão operacional de condições.  
✔️ **Coleta**: Open-Meteo (forecast + histórico).  
✔️ **Armazenamento**: DuckDB.  
✔️ **Análise**: gráficos, timeline, métricas e condições.  
✔️ **Processamento**: feature engineering (lags, cíclicos, janelas).  
✔️ **Modelagem (opcional)**: baseline vs. modelo, métricas, artefatos salvos.  
✔️ **Deploy**: Streamlit (UI) + FastAPI (ingestão).  
✔️ **Documentação**: passo-a-passo de execução atualizado.

---

## Licença
Uso educacional/experimental. Dados por **Open-Meteo** (ver termos no site oficial).
