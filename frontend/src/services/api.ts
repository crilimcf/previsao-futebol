from fastapi import FastAPI, Header, HTTPException
import os
import json

app = FastAPI(title="Football Prediction API")

API_KEY = os.getenv("ENDPOINT_API_KEY", "dev-key")

def verify_token(auth_header: str):
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = auth_header.replace("Bearer ", "").strip()
    if token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


@app.get("/predictions")
def get_predictions(authorization: str = Header(None)):
    verify_token(authorization)
    try:
        with open("data/predict/predictions.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        return []

@app.get("/stats")
def get_stats(authorization: str = Header(None)):
    verify_token(authorization)
    try:
        with open("data/stats/prediction_stats.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        return {}

@app.get("/meta/last-update")
def last_update(authorization: str = Header(None)):
    verify_token(authorization)
    from datetime import datetime
    return {"last_update": datetime.utcnow().isoformat()}

@app.get("/")
def root():
    return {"status": "ok", "message": "Football Prediction API online"}
