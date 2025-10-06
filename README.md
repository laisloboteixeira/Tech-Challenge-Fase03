# 🌡️ Tech Challenge – Fase 3 (FIAP)
## Previsão de Temperatura **e Condições em Tempo Real**
*(Open-Meteo + FastAPI + DuckDB + Streamlit)*

Projeto completo para **coletar dados horários de clima**, armazenar em **DuckDB**, **treinar um modelo de ML** e disponibilizar um **dashboard interativo (Streamlit)**. Inclui **condições do tempo (WMO)**, **probabilidade de chuva**, **cobertura de nuvens**, **sensação térmica**, **timeline das próximas 6h** e **gráfico de probabilidade**.

---

## 🔗 Sumário
- [Vídeo demonstrativo](#vídeo-demonstrativo)
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
- [Equipe](#equipe)
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
```text
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
```text
├── data/
│   ├── refined/                     # features .parquet (gerado)
│   └── rt_weather.duckdb            # banco DuckDB (gerado)
├── models/
│   ├── model.pkl
│   └── feature_cols.json
├── scripts/
│   └── migrate_duckdb.py
├── src/
│   ├── ingestion/
│   │   └── api.py
│   ├── processing/
│   │   └── prepare_data.py
│   ├── training/
│   │   └── train.py
│   └── app/
│       ├── app.py
│       └── conditions.py
├── requirements.txt
└── README.md
```
---

## Pré-requisitos
- **Python 3.11+** (Windows 11 recomendado; funciona em Linux/macOS)
- **Pip** e **Git**

---

## Equipe

| Integrante                   | RM      | Contato                               |
|-----------------------------|---------|----------------------------------------|
| **Laís Lobo Teixeira**      | 363124  | [laisloboteixeira@gmail.com](mailto:laisloboteixeira@gmail.com) |
| **Bruno Oliveira Fermino**  | 363137  | [of.bruno9@hotmail.com](mailto:of.bruno9@hotmail.com) |
| **Victor Rodrigues Linhati**| 363151  | [victor_linhati@hotmail.com](mailto:victor_linhati@hotmail.com) |

---

## Licença
Uso educacional/experimental.  
Dados fornecidos por **[Open-Meteo](https://open-meteo.com/)** sob seus respectivos termos.
