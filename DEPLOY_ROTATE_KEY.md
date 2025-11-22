Rotate Render API key and add to GitHub Secrets

1) Rotate the Render API key (in Render dashboard)

- Open https://dashboard.render.com
- Sign in and go to "Account Settings" -> "API Keys" (or equivalent)
- Revoke the old API key you pasted into chat.
- Create a new API key and copy it immediately (you won't see it again).

2) Add the new key to GitHub repository secrets

Option A (recommended, via GitHub UI):
- Go to your repo Settings -> Secrets and variables -> Actions -> New repository secret
- Add `RENDER_API_KEY` with the new key value
- Add `RENDER_SERVICE_ID` with the service id (value looks like `srv-xxxx`)
- (Optional) Add `GHCR_PAT` if you want the workflow to push images (Personal Access Token)

Option B (via GitHub CLI):
- Install GitHub CLI: https://github.com/cli/cli
- Authenticate: `gh auth login`
- Run from the repo root:

```bash
./scripts/set_github_secret.sh RENDER_API_KEY "<new-key-value>"
./scripts/set_github_secret.sh RENDER_SERVICE_ID "srv-..."
# optionally
./scripts/set_github_secret.sh GHCR_PAT "<pat>"
```

3) Quick test: trigger the helper script locally to ensure the key works

PowerShell (Windows):

```powershell
$env:RENDER_API_KEY = '<new-key>'
$env:RENDER_SERVICE_ID = 'srv-xxxx'
.\scripts\trigger_render_deploy.ps1
```

Bash (Linux / WSL / Git Bash):

```bash
export RENDER_API_KEY='<new-key>'
export RENDER_SERVICE_ID='srv-xxxx'
./scripts/trigger_render_deploy.sh
```

4) After successful verification:
- Remove any keys you published in chat immediately from Render (rotate them).
- Ensure GitHub Secrets contain the new values.

If you want, I can continue and:
- Poll the current deploy until terminal state and run the health/predictions checks (I already have a deploy id recorded), OR
- Guide you through the rotation interactively while you paste the new key here (not recommended; paste only if you accept the security risk). 
