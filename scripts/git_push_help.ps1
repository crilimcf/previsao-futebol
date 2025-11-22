# Helper script to commit and push changes to GitHub
# Usage: run from repository root in PowerShell
# $ ./scripts/git_push_help.ps1

param(
  [string]$Branch = "main",
  [string]$Message = "chore: apply postprocess + frontend fixes; add deploy/validation workflows and helper scripts",
  [switch]$CreatePR
)

function Abort($msg) {
  Write-Host "ERROR: $msg" -ForegroundColor Red
  exit 1
}

# Ensure git is available
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Abort "git not found in PATH. Install Git and try again."
}

# Show status and ask confirmation
Write-Host "Git status (por favor verifique as alterações):" -ForegroundColor Cyan
git status --porcelain
Write-Host "\nWill add all changes, commit and push to branch: $Branch" -ForegroundColor Yellow

$ok = Read-Host "Continuar? (s/N)"
if ($ok -ne 's' -and $ok -ne 'S') {
  Write-Host "Aborting by user." -ForegroundColor Yellow
  exit 0
}

# Configure user if not set
$uname = git config user.name
$uemail = git config user.email
if (-not $uname) {
  $unameIn = Read-Host "Git user.name não configurado. Insira um nome (ou Enter para manter)"
  if ($unameIn) { git config user.name "$unameIn" }
}
if (-not $uemail) {
  $uemailIn = Read-Host "Git user.email não configurado. Insira um email (ou Enter para manter)"
  if ($uemailIn) { git config user.email "$uemailIn" }
}

try {
  git add -A
  git commit -m "$Message"
} catch {
  Write-Host "Nenhum commit criado (talvez não há mudanças a commitar): $_" -ForegroundColor Yellow
}

# Ensure we are on desired branch
$current = git rev-parse --abbrev-ref HEAD
if ($current -ne $Branch) {
  Write-Host "Atualmente na branch '$current'. Irei tentar commitar e enviar para '$Branch'." -ForegroundColor Yellow
  git checkout -B $Branch
}

# Pull latest (rebase) then push
try {
  Write-Host "Fazendo git pull --rebase origin $Branch" -ForegroundColor Cyan
  git pull --rebase origin $Branch
} catch {
  Write-Host "git pull --rebase falhou: $_" -ForegroundColor Yellow
}

Write-Host "Pushing to origin/$Branch" -ForegroundColor Cyan
try {
  git push origin $Branch
  Write-Host "Push concluído com sucesso." -ForegroundColor Green
} catch {
  Abort "git push falhou: $_"
}

if ($CreatePR) {
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "gh CLI não encontrado; não é possível criar PR automaticamente." -ForegroundColor Yellow
  } else {
    Write-Host "Criando Pull Request via gh..." -ForegroundColor Cyan
    gh pr create --title "Fix: postprocess/frontend and deploy automation" --body "Automated PR: apply fixes and add deploy/validation workflow" --base main --head $Branch
  }
}
