## 📘 `previsao-futebol` — README.md (proposta)

```md
# Previsão de Futebol

Stack: **FastAPI (backend)** + **Next.js (frontend)** + **Proxy para API-Football** (via serviço dedicado) + **tarefas agendadas** (scripts `run_daily.py`, `run_weekly.py`).

> Objetivo: obter dados da API-Football, normalizar/guardar, expor endpoints para o frontend, e apresentar previsões/estatísticas no site.

## Arquitetura
- `src/` — código FastAPI (endpoints, serviços, modelos Pydantic)
- `scripts/` — tarefas programadas (ex.: `run_daily.py`, `run_weekly.py`)
- `models/` — modelos de ML/artefatos
- `notebooks/` — exploração/EDA
- `frontend/` — aplicação Next.js
- `tests/` — testes automáticos (Python)

## Variáveis de ambiente
> Mantém **segredos fora do Git**. Usa *Render Environment* (ou GitHub Secrets) para chaves.

### Comuns / Dados
- `ENV` — `production` | `development` (padrão: `development`)
- `REDIS_URL` — URL Redis (ex.: `rediss://...`)

### Backend (FastAPI)
- `APISPORTS_PROXY_BASE` — Base URL do **proxy** para API-Football (ex.: `https://football-proxy.onrender.com`)
- `API_FOOTBALL_BASE` — (opcional) base da API original, padrão `https://v3.football.api-sports.io/`
- `API_FOOTBALL_SEASONS` — ex.: `2024,2025`

> **Não** definas `API_FOOTBALL_KEY` no frontend. O acesso deve ser **sempre** via backend/proxy.

### Frontend (Next.js)
- `NEXT_PUBLIC_API_BASE_URL` — base dos endpoints **do backend deste projeto**, ex.: `https://previsao-futebol.onrender.com`

> Evita tokens `NEXT_PUBLIC_*`. Tudo sensível deve ficar **server-side**.

## Desenvolvimento local
```bash
# 1) Backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -U pip
pip install -r requirements.txt  # ou pip install -e . se houver pyproject.toml
uvicorn src.main:app --reload --port 8000

# 2) Frontend
cd frontend
npm ci
npm run dev  # http://localhost:3000
```

## Testes & Lint
```bash
# Python
ruff check .
pytest -q

# Frontend (se existir)
cd frontend
npm run lint
npm test --if-present
```

## Deploy
- **Backend/Frontend**: Render (ou Docker) — configurar `REDIS_URL`, `APISPORTS_PROXY_BASE` e `NEXT_PUBLIC_API_BASE_URL`.
- **Tarefas**: usar Cron Jobs do Render para chamar `scripts/run_daily.py` e `scripts/run_weekly.py` ou endpoints internos de manutenção.

## Endpoints úteis
- `GET /health` — healthcheck (recomendado implementar)
- `GET /predictions` — previsões (expor conforme o modelo)
- `GET /stats` — estatísticas
```

---
