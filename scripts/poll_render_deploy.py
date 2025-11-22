#!/usr/bin/env python3
"""
Poll a Render deploy until terminal state and, if live, run health checks.
Usage:
  python scripts/poll_render_deploy.py dep-xxxx
or set env var DEPLOY_ID and run without args.

Requires `requests`.
"""
import os
import sys
import time
import json

try:
    import requests
except Exception:
    print("Missing dependency 'requests'. Install with: python -m pip install requests")
    sys.exit(2)

RENDER_API = "https://api.render.com/v1"
PUBLIC_URL = "https://previsao-futebol.onrender.com"
KEY = os.environ.get("RENDER_API_KEY")
SVC = os.environ.get("RENDER_SERVICE_ID")

if not KEY:
    print("Set RENDER_API_KEY environment variable before running.")
    sys.exit(2)


def get_deploy(deploy_id):
    # First try direct deploy lookup
    url = f"{RENDER_API}/deploys/{deploy_id}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {KEY}"}, timeout=15)
    if resp.ok:
        return resp.json()

    # If not found, fallback to listing service deploys and search by id
    if resp.status_code == 404:
        print("Direct /deploys/{id} returned 404; falling back to /services/{svc}/deploys list")
        list_url = f"{RENDER_API}/services/{SVC}/deploys?limit=50"
        r2 = requests.get(list_url, headers={"Authorization": f"Bearer {KEY}"}, timeout=15)
        if not r2.ok:
            try:
                print(json.dumps(r2.json(), indent=2))
            except Exception:
                print(r2.text)
            r2.raise_for_status()
        items = r2.json()
        for it in items:
            if it.get("id") == deploy_id:
                return it
        # not found in list either
        print("Deploy id not found in service deploys list")
        resp.raise_for_status()

    # Other non-OK status: print body and raise
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    resp.raise_for_status()


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
    if len(sys.argv) > 1:
        deploy_id = sys.argv[1]
    else:
        deploy_id = os.environ.get("DEPLOY_ID")
    if not deploy_id:
        print("Usage: python scripts/poll_render_deploy.py <deploy-id> or set DEPLOY_ID env var")
        sys.exit(2)

    print("Polling deploy:", deploy_id)
    deadline = time.time() + 20 * 60
    while time.time() < deadline:
        try:
            d = get_deploy(deploy_id)
        except Exception as e:
            print("Error fetching deploy:", e)
            time.sleep(5)
            continue
        state = d.get("state")
        print(time.strftime('%Y-%m-%d %H:%M:%S'), "state:", state)
        if state in ("live", "failed", "cancelled"):
            print("Final deploy object:\n")
            print(json.dumps(d, indent=2))
            if state == "live":
                run_health_checks()
            else:
                print("Deploy finished with state:", state)
            return
        time.sleep(8)
    print("Timed out waiting for deploy to reach terminal state")


if __name__ == '__main__':
    main()
