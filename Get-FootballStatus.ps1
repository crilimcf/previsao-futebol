# ==========================================================
# Get-FootballStatus.ps1
# Atualiza ficheiro de previsões e notifica o backend Render
# ==========================================================

# ⚽ CONFIGURAÇÃO
$ApiKey = $env:APISPORTS_KEY
if (-not $ApiKey) {
    Write-Host "API key não encontrada. Executa: setx APISPORTS_KEY \"tua_chave_aqui\"" -ForegroundColor Yellow
    exit
}

$baseUrl = "https://v3.football.api-sports.io"
$outputPath = "data\predict\predictions.json"

# Backend Render
$backendUrl = "https://previsao-futebol.onrender.com/meta/update"
$token = "d110d6f22b446c54deadcadef7b234f6966af678"

# Criar pasta se não existir
$pasta = Split-Path $outputPath -Parent
if (-not (Test-Path $pasta)) { New-Item -ItemType Directory -Force -Path $pasta | Out-Null }

# ----------------------------------------------------------
function Get-ApiStatus {
# ----------------------------------------------------------
    Write-Host "`n[STATUS] Testando estado da API-Football..." -ForegroundColor Cyan
    try {
        $status = Invoke-RestMethod -Uri "$baseUrl/status" -Headers @{ "x-apisports-key" = $ApiKey }
        $acc = $status.response.account
        $sub = $status.response.subscription
        Write-Host ("Conta: {0} {1} ({2})" -f $acc.firstname, $acc.lastname, $acc.email)
        Write-Host ("Plano: {0}" -f $sub.plan)
        Write-Host ("Limite diário: {0}" -f $status.response.requests.limit_day)
        Write-Host ("Expira em: {0}" -f $sub.end)
    }
    catch {
        Write-Host ("Erro ao obter status: {0}" -f $_.Exception.Message) -ForegroundColor Red
    }
}

# ----------------------------------------------------------
function Get-TodayMatches {
# ----------------------------------------------------------
    Write-Host "`n[FETCH] Procurando jogos para hoje..." -ForegroundColor Cyan
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $uri = "$baseUrl/fixtures?date=$today"

    try {
        $fixtures = Invoke-RestMethod -Uri $uri -Headers @{ "x-apisports-key" = $ApiKey }
        return $fixtures.response
    }
    catch {
        Write-Host "Erro ao buscar jogos: $($_.Exception.Message)" -ForegroundColor Red
        return @()
    }
}

# ----------------------------------------------------------
function Update-Backend {
# ----------------------------------------------------------
    param ($url, $token)
    Write-Host "`n[UPLOAD] A enviar atualização ao backend..." -ForegroundColor Cyan
    try {
        $response = Invoke-RestMethod -Uri $url -Method POST -Headers @{ 
            "Authorization" = "Bearer $token"
        }
        Write-Host ("✅ Backend atualizado com sucesso: {0}" -f ($response.last_update)) -ForegroundColor Green
    }
    catch {
        Write-Host "❌ Erro ao contactar o backend: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# ----------------------------------------------------------
# Execução principal
# ----------------------------------------------------------
Get-ApiStatus

$matches = Get-TodayMatches
if ($matches.Count -eq 0) {
    Write-Host "⚠️  Nenhum jogo encontrado hoje." -ForegroundColor Yellow
} else {
    Write-Host ("✅ {0} jogos encontrados. Gravando ficheiro..." -f $matches.Count) -ForegroundColor Green

    # Extrair apenas campos essenciais
    $simplified = $matches | ForEach-Object {
        [PSCustomObject]@{
            fixture_id = $_.fixture.id
            date       = $_.fixture.date
            league_id  = $_.league.id
            league     = $_.league.name
            country    = $_.league.country
            home_team  = $_.teams.home.name
            away_team  = $_.teams.away.name
            status     = $_.fixture.status.short
        }
    }

    # Salvar no JSON
    $simplified | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 $outputPath
    Write-Host ("📁 Ficheiro salvo em: {0}" -f (Resolve-Path $outputPath)) -ForegroundColor Cyan

    # 🚀 Enviar atualização ao backend Render
    Update-Backend -url $backendUrl -token $token
}

Write-Host "`n✅ Script concluído." -ForegroundColor Green
