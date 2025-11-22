# scripts/trigger_render_deploy.ps1
# Trigger Render deploy via API v1 and poll until terminal state.
# Usage: $env:RENDER_API_KEY = 'xxx'; $env:RENDER_SERVICE_ID = 'srv-...'; ./scripts/trigger_render_deploy.ps1

param()

if (-not $env:RENDER_API_KEY -or -not $env:RENDER_SERVICE_ID) {
  Write-Error "Set RENDER_API_KEY and RENDER_SERVICE_ID environment variables before running."
  exit 2
}

$key = $env:RENDER_API_KEY
$svc = $env:RENDER_SERVICE_ID
Write-Host "Triggering deploy for service $svc"

$body = '{"clearCache": true}'

try {
  $resp = curl.exe -s -S -X POST -H "Authorization: Bearer $key" -H "Content-Type: application/json" -d $body "https://api.render.com/v1/services/$svc/deploys" | Out-String
} catch {
  Write-Error "Failed to call Render API: $_"
  exit 1
}

try {
  $j = $resp | ConvertFrom-Json
} catch {
  Write-Error "Failed to parse Render response: $resp"
  exit 1
}

$deploy_id = $j.id
if (-not $deploy_id) {
  Write-Error "No deploy id returned"
  $resp
  exit 1
}

Write-Host "Deploy created: $deploy_id"

# Poll deploy status until finished
while ($true) {
  Start-Sleep -Seconds 5
  try {
    $listRaw = curl.exe -s -H "Authorization: Bearer $key" "https://api.render.com/v1/services/$svc/deploys?limit=10" | Out-String
  } catch {
    Write-Host "Failed to fetch deploy list: $_"
    continue
  }

  try {
    $lj = $listRaw | ConvertFrom-Json
  } catch {
    Write-Host "Failed to parse list JSON, retrying..."
    continue
  }

  $item = $lj | Where-Object { $_.id -eq $deploy_id }
  if (-not $item) {
    Write-Host "Deploy not found yet; sleeping..."
    continue
  }

  Write-Host "Deploy state: $($item.state)"
  if ($item.state -in @('live','failed','cancelled')) {
    $item | ConvertTo-Json -Depth 10
    break
  }
}

# If deploy is live, run basic health checks against public URL
if ($item.state -eq 'live') {
  Write-Host "`n== Deploy is LIVE: running health checks against https://previsao-futebol.onrender.com =="
  try {
    Write-Host "GET /healthz ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/healthz" | Write-Host
  } catch { Write-Host "Healthz request failed: $_" }

  try {
    Write-Host "`nGET /predictions (sample) ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/predictions?date=2025-11-22&limit=5" | Write-Host
  } catch { Write-Host "Predictions v1 request failed: $_" }

  try {
    Write-Host "`nGET /predictions/v2 (sample) ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/predictions/v2?date=2025-11-22&limit=5" | Write-Host
  } catch { Write-Host "Predictions v2 request failed: $_" }
} else {
  Write-Host "Deploy finished with state: $($item.state)"
}

#!/usr/bin/env pwsh
# Trigger Render deploy via API v1 and poll until terminal state.
# Usage: in PowerShell: $env:RENDER_API_KEY = 'xxx'; $env:RENDER_SERVICE_ID = 'srv-...'; .\scripts\trigger_render_deploy.ps1

param()

if (-not $env:RENDER_API_KEY -or -not $env:RENDER_SERVICE_ID) {
  Write-Error "Set RENDER_API_KEY and RENDER_SERVICE_ID environment variables before running."
  exit 2
}

$key = $env:RENDER_API_KEY
$svc = $env:RENDER_SERVICE_ID
Write-Host "Triggering deploy for service $svc"

$body = '{"clearCache": true}'

try {
  $resp = curl.exe -s -S -X POST -H "Authorization: Bearer $key" -H "Content-Type: application/json" -d $body "https://api.render.com/v1/services/$svc/deploys" | Out-String
} catch {
  Write-Error "Failed to call Render API: $_"
  exit 1
}

try {
  $j = $resp | ConvertFrom-Json
} catch {
  Write-Error "Failed to parse Render response: $resp"
  exit 1
}

$deploy_id = $j.id
if (-not $deploy_id) {
  Write-Error "No deploy id returned"
  $resp
  exit 1
}

Write-Host "Deploy created: $deploy_id"

# Poll deploy status until finished
while ($true) {
  Start-Sleep -Seconds 5
  try {
    $listRaw = curl.exe -s -H "Authorization: Bearer $key" "https://api.render.com/v1/services/$svc/deploys?limit=10" | Out-String
  } catch {
    Write-Host "Failed to fetch deploy list: $_"
    continue
  }

  try {
    $lj = $listRaw | ConvertFrom-Json
  } catch {
    Write-Host "Failed to parse list JSON, retrying..."
    continue
  }

  $item = $lj | Where-Object { $_.id -eq $deploy_id }
  if (-not $item) {
    Write-Host "Deploy not found yet; sleeping..."
    continue
  }

  Write-Host "Deploy state: $($item.state)"
  if ($item.state -in @('live','failed','cancelled')) {
    $item | ConvertTo-Json -Depth 10
    break
  }
}

# If deploy is live, run basic health checks against public URL
if ($item.state -eq 'live') {
  Write-Host "`n== Deploy is LIVE: running health checks against https://previsao-futebol.onrender.com =="
  try {
    Write-Host "GET /healthz ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/healthz" | Write-Host
  } catch { Write-Host "Healthz request failed: $_" }

  try {
    Write-Host "`nGET /predictions (sample) ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/predictions?date=2025-11-22&limit=5" | Write-Host
  } catch { Write-Host "Predictions v1 request failed: $_" }

  try {
    Write-Host "`nGET /predictions/v2 (sample) ->"
    curl.exe -sS -H "Accept: application/json" "https://previsao-futebol.onrender.com/predictions/v2?date=2025-11-22&limit=5" | Write-Host
  } catch { Write-Host "Predictions v2 request failed: $_" }
} else {
  Write-Host "Deploy finished with state: $($item.state)"
}


















}  }    break    $item | ConvertTo-Json -Depth 10  if ($item.state -in @('live','failed','cancelled')) {  Write-Host "Deploy state: $($item.state)"  if (-not $item) { Write-Host "Deploy not found yet"; continue }  $item = $lj | Where-Object { $_.id -eq $deploy_id }  try { $lj = $list | ConvertFrom-Json } catch { Write-Host "Failed to parse list"; continue }  $list = curl.exe -s -H "Authorization: Bearer $key" "https://api.render.com/v1/services/$svc/deploys?limit=5" | Out-String  Start-Sleep -Seconds 5while ($true) {Write-Host "Deploy created: $deploy_id"}  exit 1  $resp  Write-Error "No deploy id returned"nif (-not $deploy_id) {