cd "C:\Users\marti\Desktop\football\football-prediction"; `
git add .; `
git commit -m ("auto: rebuild Render " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")); `
git push origin main; `
Write-Host "`n🚀 Aguardando 60s para Render rebuild...`n" -ForegroundColor Yellow; `
Start-Sleep -Seconds 60; `
curl https://previsao-futebol.onrender.com/predictions
