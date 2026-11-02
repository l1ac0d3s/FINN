# Refreshes the hosted FINN app in one go. Run from the finn folder:
#   .\refresh_finn.ps1
# It builds the seed file, sends all data to the hosted server now, and tells you
# what to upload to GitHub so the data survives future redeploys.

.venv\Scripts\Activate.ps1
$env:FINN_SERVER_URL = "https://finn-wq09.onrender.com"
$env:FINN_SYNC_TOKEN = Read-Host "Paste the FINN_SYNC_TOKEN you gave Render"

Write-Host "1/2 Building the seed file..." -ForegroundColor Cyan
python -m ingest.make_seed
if ($LASTEXITCODE -ne 0) { Write-Host "Seed step failed. Send me the red text above." -ForegroundColor Red; exit 1 }

Write-Host "2/2 Sending all data to the hosted server..." -ForegroundColor Cyan
python -m ingest.publish --full
if ($LASTEXITCODE -ne 0) { Write-Host "Publish failed. Send me the red text above." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Done. Next: upload the folders server, shared, web, tests, ingest, seed and the file README.md to GitHub." -ForegroundColor Green
