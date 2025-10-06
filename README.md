# 🌡️ Tech Challenge – Fase 3 (FIAP)
## Previsão de Temperatura **e Condições em Tempo Real**
*(Open-Meteo + FastAPI + DuckDB + Streamlit)*

Projeto completo para **coletar dados horários de clima**, armazenar em **DuckDB**, **treinar um modelo de ML** e disponibilizar um **dashboard interativo (Streamlit)**.  
Inclui **condições do tempo (WMO)**, **probabilidade de chuva**, **cobertura de nuvens**, **sensação térmica**, **timeline das próximas 6h** e **gráfico de probabilidade** com marcador do “agora”.

---

## 🔗 Sumário
- [🎥 Vídeo demonstrativo](#-vídeo-demonstrativo)
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

## 🎥 Vídeo demonstrativo
> Clique na imagem abaixo para assistir à demonstração completa do projeto no YouTube:

[![Tech Challenge – Fase 3 (FIAP)](https://img.youtube.com/vi/U8TE81XCi4A/maxresdefault.jpg)](https://youtu.be/U8TE81XCi4A)

---

## Visão geral
- **Coleta**: via **FastAPI** usando **Open-Meteo** (previsão e histórico).  
- **Armazenamento**: **DuckDB** em `data/rt_weather.duckdb` (tabela `raw.weather_hourly`).  
- **Processamento (ML opcional)**: `src/processing/prepare_data.py` gera *features* em Parquet.  
- **Modelagem (ML opcional)**: `src/training/train.py` treina o modelo e salva artefatos.  
- **Aplicação (UI)**: `src/app/app.py` (Streamlit) para:  
  - selecionar cidade/coords e acionar **coleta/backfill** pela API;  
  - visualizar **condições atuais**, **próxima hora**, **próximas 6h**;  
  - exibir **gráfico de probabilidade de chuva** (0–100%) com marcador do “agora”;  
  - (opcional) prever a **próxima hora** com modelo treinado.

---

## Arquitetura
Open-Meteo (forecast/archive)
│
▼
FastAPI (/collect, /backfill) ───► DuckDB (raw.weather_hourly)
│ │
│ └─► Parquet (features) [prepare_data.py]
│
└────────► Streamlit (app.py) ◄─────────┐
• condições “agora”/“próxima hora” │
• próximas 6h (emojis) ├─ (opcional) usa modelo treinado
• gráfico prob. de chuva (0–100%) │
• exportações ┘

---

## Estrutura do repositório
├── data/
│ ├── refined/ # features .parquet (gerado)
│ └── rt_weather.duckdb # banco DuckDB (gerado)
├── models/ # modelos/artefatos (gerados)
│ ├── model.pkl
│ └── feature_cols.json
├── scripts/
│ └── migrate_duckdb.py # migração de schema (opcional)
├── src/
│ ├── ingestion/
│ │ └── api.py # FastAPI (coleta/backfill + persistência)
│ ├── processing/
│ │ └── prepare_data.py # gera features a partir do DuckDB
│ ├── training/
│ │ └── train.py # treina modelo e salva artefatos
│ └── app/
│ ├── app.py # dashboard Streamlit
│ └── conditions.py # seção de condições (UI)
├── requirements.txt
└── README.md
---

## Pré-requisitos
- **Python 3.11+** (Windows 11 recomendado; funciona em Linux/macOS)
- **Pip** e **Git**

---

## Setup rápido
### Windows (PowerShell)
\`\`\`powershell
git clone https://github.com/laisloboteixeira/Tech-Challenge-Fase03.git
cd Tech-Challenge-Fase03
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# se precisar complementar:
pip install streamlit fastapi uvicorn duckdb pandas requests altair
\`\`\`

### Linux/macOS (bash)
\`\`\`bash
git clone https://github.com/laisloboteixeira/Tech-Challenge-Fase03.git
cd Tech-Challenge-Fase03
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
\`\`\`

---

## Como rodar

### 1) Subir a API (FastAPI)
\`\`\`powershell
uvicorn src.ingestion.api:app --reload --host 127.0.0.1 --port 8000
\`\`\`

### 2) Trazer dados (Backfill / Collect)
**Exemplo – São Paulo (últimos 30 dias):**
\`\`\`powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/backfill?latitude=-23.55&longitude=-46.63&days=30"
\`\`\`

### 3) Preparar features (ML opcional)
\`\`\`powershell
$env:PYTHONPATH = (Get-Location)
python -m src.processing.prepare_data
\`\`\`

### 4) Treinar o modelo (ML opcional)
\`\`\`powershell
python -m src.training.train
\`\`\`

### 5) Rodar o app (Streamlit)
\`\`\`powershell
streamlit run src/app/app.py
\`\`\`

---

## Endpoints da API
Base: `http://127.0.0.1:8000`  
Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Esquema do banco (DuckDB)
| coluna | tipo | descrição |
|--------|------|-----------|
| ts | TIMESTAMP | hora UTC (naive) |
| latitude | DOUBLE | lat normalizada |
| longitude | DOUBLE | lon normalizada |
| temperature_2m | DOUBLE | temperatura (°C) |
| relative_humidity_2m | DOUBLE | umidade (%) |
| precipitation | DOUBLE | precipitação (mm) |
| wind_speed_10m | DOUBLE | vento (km/h) |
| weathercode | SMALLINT | código WMO |
| precipitation_probability | DOUBLE | prob. de chuva (%) |
| cloudcover | DOUBLE | cobertura de nuvens (%) |

---

## Dashboard / App (UI)
- **Condições atuais:** emoji + descrição (`weathercode`), sensação térmica, probabilidade de chuva e cobertura de nuvens.  
- **Timeline de 6h:** previsões horárias com ícones e percentuais.  
- **Gráfico de probabilidade:** barras (0–100%) com marcador do “agora”.  
- **Previsão ML:** card aparece se o modelo existir (`models/model.pkl`).

---

## Critérios do Tech Challenge
✔️ **Problema real (série temporal)**  
✔️ **Coleta automatizada (API)**  
✔️ **Banco local (DuckDB)**  
✔️ **Feature Engineering + ML**  
✔️ **Dashboard interativo (Streamlit)**  
✔️ **Documentação completa e funcional**  
✔️ **Vídeo demonstrativo (YouTube)**  

---

## Licença
Uso educacional/experimental.  
Dados fornecidos por **[Open-Meteo](https://open-meteo.com/)** sob seus respectivos termos.
