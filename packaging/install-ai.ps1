$ErrorActionPreference = "Stop"
$model = "qwen3:1.7b"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"

if (-not (Test-Path $ollama)) {
    Write-Host "Ollama o'rnatilmoqda..."
    winget install --exact --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
}

if (-not (Test-Path $ollama)) {
    throw "Ollama o'rnatilmadi. Uni ollama.com saytidan o'rnatib, modelni qayta yuklang."
}

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}

Write-Host "$model lokal AI modeli yuklanmoqda. Bu bir necha daqiqa olishi mumkin..."
& $ollama pull $model
if ($LASTEXITCODE -ne 0) {
    throw "AI modelini yuklash yakunlanmadi."
}
Write-Host "AI yordamchi tayyor."
