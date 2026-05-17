$env:CLOUDSDK_ACTIVE_CONFIG_NAME="business-intel-1bt"
$env:GOOGLE_GENAI_USE_VERTEXAI="TRUE"
$env:GOOGLE_CLOUD_PROJECT="business-intel-123"
$env:GOOGLE_CLOUD_LOCATION="us-central1"

Write-Host "Starting ADK Web with Google Cloud config: business-intel-1bt" -ForegroundColor Cyan
Write-Host "Project: business-intel-123" -ForegroundColor Cyan
Write-Host "Location: us-central1" -ForegroundColor Cyan

cd D:\gaps\Business_Intel
adk web
