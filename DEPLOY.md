# Deploy & Environment Notes

This document collects the minimum steps and environment variables required to run and deploy the previsao-futebol project.

1) Environment variables (example):

  - `API_FOOTBALL_KEY` : (optional) API-Football key for direct API calls. If not set, the proxy may be used.
  - `API_FOOTBALL_BASE` : base URL for API-Football (default `https://v3.football.api-sports.io/`).
  - `API_PROXY_URL` : (optional) the proxy base URL (if you deploy a proxy to avoid exposing keys to the frontend).
  - `API_PROXY_TOKEN` : (optional) secret token used by the proxy.
  - `API_FOOTBALL_SEASON` : season year used for club fixtures (e.g. `2025`).
  - `ML_LAYER_ENABLED` : `true`/`false` to enable optional ML over/2.5 layer.
  - `REDIS_URL` / `REDIS_TLS_URL` : (optional) Redis connection for caching (recommended for production).

2) Run locally (backend)

  Create a virtualenv and install requirements:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

  Run the pipeline (example):

  ```powershell
  python -m src.api_fetch_pro
  python scripts/run_postprocess_audit.py
  python scripts/apply_postprocess_safe.py
  ```

3) Frontend (Next.js)

  ```powershell
  cd frontend
  npm ci
  npm run build
  npm run start
  ```

4) CI / Production notes

  - Ensure `API_FOOTBALL_KEY` or proxy variables are set in secrets; do NOT commit keys to repo.
  - Ensure Redis is configured in production to reduce API usage and speed up scorer lookups.
  - We added smoothing to postprocess and scorer-prob caps to avoid extreme probabilities which break UX.

5) Troubleshooting

  - If `probable_scorers` lists are empty, check that the API/proxy returns squads and injuries; fallback uses `top_scorers` but may be empty.
  - Run `python scripts/check_predictions.py` and `python scripts/analyze_predictions_consistency.py` to produce quick reports in `tmp/`.

6) Rollback

  - Backups of applied predictions are kept in `backups/` when `apply_postprocess_safe.py` runs. Restore by copying desired backup to `data/predict/predictions.json`.

---
If you want I can also generate a minimal CI workflow (GitHub Actions) to run tests + build on PRs.
