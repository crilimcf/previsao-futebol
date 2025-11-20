# Instruções Copilot para `previsao-futebol`

## Visão Geral do Projeto
- **Backend:** FastAPI (Python) em `src/` — fornece endpoints de API, processamento de dados e integração de ML.
- **Frontend:** Next.js (TypeScript) em `frontend/` — consome endpoints do backend, exibe previsões e estatísticas.
- **Proxy:** Serviço dedicado para API-Football, acessado via backend (nunca diretamente do frontend).
- **Tarefas Agendadas:** Scripts Python em `scripts/` (ex.: `run_daily.py`, `run_weekly.py`) para ETL, atualizações e jobs em lote.
- **Modelos de ML & Dados:** Artefatos em `models/`, dados em `data/`, e EDA em `notebooks/`.

## Convenções e Padrões
- **Variáveis de Ambiente:**
  - Segredos e chaves de API nunca são expostos ao frontend. Use backend/proxy para operações sensíveis.
  - Veja `README.md` para variáveis obrigatórias (ex.: `APISPORTS_PROXY_BASE`, `NEXT_PUBLIC_API_BASE_URL`).
- **Estrutura Backend:**
  - Endpoints: `src/api_routes/`
  - Lógica principal: `src/` (ex.: `predict.py`, `features.py`, `data_prep.py`)
  - Utilitários: `src/utils/`
- **Estrutura Frontend:**
  - Código do app: `frontend/src/app/`
  - Lógica compartilhada: `frontend/src/lib/`, `frontend/src/services/`
  - Componentes: `frontend/src/components/`
- **Fluxo de Dados:**
  - Todos os dados externos de futebol são buscados via proxy, processados no backend e expostos ao frontend via REST.
  - Previsões de ML são geradas no backend e salvas em `data/predict/` ou `models/`.

## Fluxos de Trabalho
- **Backend:**
  - Crie venv, instale com `pip install -r requirements.txt`.
  - Rode: `uvicorn src.main:app --reload --port 8000`
  - Teste: `pytest -q`, lint: `ruff check .`
- **Frontend:**
  - `cd frontend && npm ci && npm run dev`
  - Lint: `npm run lint`, teste: `npm test --if-present`
- **Tarefas Agendadas:**
  - Execute scripts em `scripts/` para ETL, atualizações e treinamento de modelos.

## Pontos de Integração
- **API-Football:** Sempre acessada via proxy backend (`proxy_apifootball.py`).
- **Modelos de ML:** Treinados e usados no backend (`src/ml/`, `src/models/`).
- **Frontend/Backend:** Comunicação via endpoints REST (veja `src/api_routes/`).

## Notas Específicas do Projeto
- **Nunca exponha chaves ou segredos no frontend.**
- **Todo acesso a dados e lógica de previsão deve passar pelo backend/proxy.**
- **Siga a estrutura de diretórios para novos scripts, modelos e componentes.**
- **Use scripts existentes como base para novos jobs ETL/modelos.**

## Referências
- Veja `README.md` para detalhes de setup, ambiente e fluxos.
- Exemplo de endpoint backend: `src/api_routes/predict.py`
- Exemplo de job agendado: `scripts/run_daily.py`
- Exemplo de lógica de ML: `src/ml/`, `src/predictor_bivar.py`
