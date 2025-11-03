from fastapi import FastAPI, Request

app = FastAPI()

# --- rota temporária para descobrir o IP público ---
@app.get("/myip")
async def get_my_ip(request: Request):
    return {"ip": request.client.host}
# ----------------------------------------------------

from fastapi.responses import JSONResponse

PROXY_TOKEN = "CF_Proxy_2025_Secret_!@#839"

@app.middleware("http")
async def check_token(request: Request, call_next):
    if request.url.path == "/myip":
        # não exige token para o endpoint de debug
        return await call_next(request)

    token = request.headers.get("x-proxy-token")
    if token != PROXY_TOKEN:
        return JSONResponse(
            status_code=401,
            content={"detail": "Token inválido ou ausente"},
        )
    return await call_next(request)

@app.get("/status")
async def get_status():
    return {"status": "ok"}
