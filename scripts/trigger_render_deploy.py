#!/usr/bin/env python3
"""
Trigger Render deploy (v1 API) and poll until terminal state.
Usage:
  # set env vars in your shell first
  # Windows PowerShell:
  # $env:RENDER_API_KEY = '...'
  # $env:RENDER_SERVICE_ID = 'srv-...'
  # then run:
  # python scripts/trigger_render_deploy.py

This script uses the `requests` package. If missing, install with:
  python -m pip install requests

It POSTS to /v1/services/{SERVICE_ID}/deploys and polls /v1/services/{SERVICE_ID}/deploys
"""

import os
import sys
import time
import json
from typing import Optional

try:
    import requests
except Exception:
    print("Missing dependency 'requests'. Install with: python -m pip install requests", file=sys.stderr)
    sys.exit(2)

RENDER_API = "https://api.render.com/v1"
PUBLIC_URL = "https://previsao-futebol.onrender.com"

KEY = os.environ.get("RENDER_API_KEY")
SVC = os.environ.get("RENDER_SERVICE_ID")

if not KEY or not SVC:
    print("Set environment variables RENDER_API_KEY and RENDER_SERVICE_ID before running.")
    sys.exit(2)

HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def create_deploy() -> dict:
    url = f"{RENDER_API}/services/{SVC}/deploys"
    # First try: include clearCache flag
    payload = {"clearCache": True}
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if resp.ok:
            return resp.json()
        # if server says invalid JSON, try with empty object
        try:
            body = resp.json()
        except Exception:
            body = {"text": resp.text}
        if resp.status_code == 400 and isinstance(body, dict) and body.get("message", "").lower().find("invalid json") != -1:
            print("Server reported invalid JSON; retrying with empty JSON object")
            resp2 = requests.post(url, headers=HEADERS, json={}, timeout=30)
            if resp2.ok:
                return resp2.json()
            print(f"Retry with empty JSON failed: {resp2.status_code}")
            try:
                print(json.dumps(resp2.json(), indent=2))
            except Exception:
                print(resp2.text)
            resp2.raise_for_status()
        # fallback: show response and raise
        print(f"Render create deploy returned status {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)
        resp.raise_for_status()
    except requests.RequestException:
        raise


def get_service_info() -> dict:
    url = f"{RENDER_API}/services/{SVC}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {KEY}"}, timeout=15)
    if not resp.ok:
        print(f"Failed to fetch service info: {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)
        resp.raise_for_status()
    return resp.json()


def list_deploys(limit: int = 10) -> list:
    url = f"{RENDER_API}/services/{SVC}/deploys?limit={limit}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {KEY}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_deploy(deploy_id: str, timeout_minutes: int = 10) -> Optional[dict]:
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        try:
            items = list_deploys(limit=20)
        except Exception as e:
            print(f"Error fetching deploy list: {e}")
            time.sleep(5)
            continue

        for it in items:
            if it.get("id") == deploy_id:
                state = it.get("state")
                print(f"Deploy {deploy_id} state: {state}")
                if state in ("live", "failed", "cancelled"):
                    return it
                break

        time.sleep(5)

    print("Timeout waiting for deploy to reach terminal state")
    return None


def run_health_checks():
    print("\n== Running basic health checks against production URL ==")
    try:
        r = requests.get(f"{PUBLIC_URL}/healthz", timeout=10)
        print("GET /healthz ->", r.status_code, r.text)
    except Exception as e:
        print("healthz check failed:", e)

    try:
        r = requests.get(f"{PUBLIC_URL}/predictions?limit=5", timeout=15)
        print("GET /predictions ->", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2)[:4000])
        except Exception:
            print(r.text[:4000])
    except Exception as e:
        print("predictions v1 check failed:", e)

    try:
        r = requests.get(f"{PUBLIC_URL}/predictions/v2?limit=5", timeout=15)
        print("GET /predictions/v2 ->", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2)[:4000])
        except Exception:
            print(r.text[:4000])
    except Exception as e:
        print("predictions v2 check failed:", e)


def main():
    print("Creating deploy for service:", SVC)
    # Print service info first to help diagnose permission / config issues
    try:
        info = get_service_info()
        print("Service info:")
        print(json.dumps(info, indent=2)[:4000])
    except Exception as e:
        print("Warning: could not fetch service info:", e)

    try:
        j = create_deploy()
    except Exception as e:
        print("Failed to create deploy:", e)
        sys.exit(1)

    deploy_id = j.get("id")
    if not deploy_id:
        print("No deploy id in response:", json.dumps(j, indent=2))
        sys.exit(1)

    print("Deploy created:", deploy_id)
    print(json.dumps(j, indent=2)[:4000])

    final = poll_deploy(deploy_id, timeout_minutes=15)
    if not final:
        print("Deploy did not reach terminal state within timeout")
        sys.exit(1)

    print("Final deploy object:\n")
    print(json.dumps(final, indent=2))

    if final.get("state") == "live":
        run_health_checks()
    else:
        print("Deploy finished with state:", final.get("state"))


if __name__ == "__main__":
    main()
