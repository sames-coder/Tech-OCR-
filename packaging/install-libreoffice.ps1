$ErrorActionPreference = "Stop"
$soffice = Join-Path $env:ProgramFiles "LibreOffice\program\soffice.exe"

if (Test-Path $soffice) {
    Write-Host "LibreOffice allaqachon o'rnatilgan."
    exit 0
}

Write-Host "Eski DOC fayllari uchun LibreOffice o'rnatilmoqda..."
winget install --exact --id TheDocumentFoundation.LibreOffice --silent --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $soffice)) {
    throw "LibreOffice o'rnatilmadi. DOCX, PDF va rasmlar baribir ishlaydi."
}
Write-Host "LibreOffice tayyor."
