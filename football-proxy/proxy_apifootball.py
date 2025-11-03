from fastapi import FastAPI, Request, HTTPException
import httpx, os, logging

app = FastAPI(title="Football Proxy API", version="1.0")

# Variáveis de ambiente
API_KEY = os.getenv("APIFOOTBALL_KEY", "30e1e48fbc6d0839f42212185149c7b4")
PROXY_TOKEN = os.getenv("PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")
BASE_URL = "https://v3.football.api-sports.io"

# Logging elegante
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

@app.get("/{endpoint}")
async def proxy(endpoint: str, request: Request):
    """Proxy seguro para API-Football"""
    token = request.headers.get("x-proxy-token")
    if token != PROXY_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido ou ausente")

    params = dict(request.query_params)
    url = f"{BASE_URL}/{endpoint}"

    headers = {"x-apisports-key": API_KEY}

    logging.info(f"➡️ Proxying: {url} | params={params}")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code != 200:
        logging.warning(f"⚠️ API-Football respondeu com {response.status_code}")
        return {
            "error": response.status_code,
            "details": response.text,
            "url": url,
            "params": params
        }

    return response.json()
