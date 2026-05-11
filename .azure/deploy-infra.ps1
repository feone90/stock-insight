# StockInsight Azure 인프라 배포 스크립트.
#
# 사전:
#   - az login 완료
#   - .azure/secrets.env 채워짐
#
# 작동:
#   1. App RG 생성 (idempotent)
#   2. what-if 검증 (사용자 확인)
#   3. main.bicep deploy
#   4. 다음 step 안내 출력
#
# Idempotent — 다시 돌려도 안전 (Bicep 자체가 declarative).

param(
    [Parameter(Mandatory=$true)][string]$SubscriptionId,
    [string]$AppResourceGroup = "rg-stockinsight-dev",
    [string]$Location = "koreacentral",
    [string]$EnvironmentName = "dev"
)

$ErrorActionPreference = "Stop"

# ─── secrets.env 로드 ────────────────────────────────────────
$secretsFile = ".azure/secrets.env"
if (-not (Test-Path $secretsFile)) {
    Write-Error "Missing $secretsFile. Copy from .azure/secrets.env.example and fill in."
    exit 1
}

$secrets = @{}
Get-Content $secretsFile | ForEach-Object {
    if ($_ -match "^([^=#]+)=(.*)$") {
        $secrets[$Matches[1].Trim()] = $Matches[2].Trim()
    }
}

$required = @("POSTGRES_ADMIN_PASSWORD","GHCR_TOKEN","LLM_ENDPOINT","LLM_API_KEY","LLM_DEPLOYMENT","JWT_SECRET","ADMIN_PASSWORD")
foreach ($key in $required) {
    if (-not $secrets.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($secrets[$key])) {
        Write-Error "Missing required secret: $key (in $secretsFile)"
        exit 1
    }
}

# ─── subscription 설정 ──────────────────────────────────────
Write-Host "[1/4] Setting subscription..."
az account set --subscription $SubscriptionId

# ─── App RG 생성 (없으면) ────────────────────────────────────
Write-Host "[2/4] Ensuring resource group $AppResourceGroup..."
$ErrorActionPreference = "Continue"
$rgShow = az group show --name $AppResourceGroup 2>$null
$ErrorActionPreference = "Stop"
if (-not $rgShow) {
    az group create --name $AppResourceGroup --location $Location --output none
    Write-Host "  Created."
} else {
    Write-Host "  Exists."
}

# ─── what-if 검증 ────────────────────────────────────────────
Write-Host "[3/4] Running what-if validation..."
$secretParams = @(
    "postgresAdminPassword=$($secrets.POSTGRES_ADMIN_PASSWORD)",
    "ghcrToken=$($secrets.GHCR_TOKEN)",
    "llmEndpoint=$($secrets.LLM_ENDPOINT)",
    "llmApiKey=$($secrets.LLM_API_KEY)",
    "llmDeployment=$($secrets.LLM_DEPLOYMENT)",
    "dartApiKey=$($secrets.DART_API_KEY ?? '')",
    "fredApiKey=$($secrets.FRED_API_KEY ?? '')",
    "tavilyApiKey=$($secrets.TAVILY_API_KEY ?? '')",
    "jwtSecret=$($secrets.JWT_SECRET)",
    "adminPassword=$($secrets.ADMIN_PASSWORD)"
)

az deployment group what-if `
    --resource-group $AppResourceGroup `
    --template-file "infra/main.bicep" `
    --parameters "infra/main.parameters.json" `
    --parameters $secretParams

$confirm = Read-Host "`nProceed with deployment? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Aborted."
    exit 0
}

# ─── 실제 deploy ─────────────────────────────────────────────
Write-Host "[4/4] Deploying main.bicep (5–10분 소요)..."
$deployResult = az deployment group create `
    --resource-group $AppResourceGroup `
    --template-file "infra/main.bicep" `
    --parameters "infra/main.parameters.json" `
    --parameters $secretParams `
    --query "properties.outputs" -o json | ConvertFrom-Json

$webAppName = $deployResult.webAppName.value
$webAppUrl = $deployResult.webAppUrl.value

Write-Host ""
Write-Host "==============================================="
Write-Host "Deploy 완료!"
Write-Host "==============================================="
Write-Host "  Web App name: $webAppName"
Write-Host "  Web App URL:  $webAppUrl"
Write-Host "  Postgres FQDN: $($deployResult.postgresFqdn.value)"
Write-Host ""
Write-Host "다음 step:"
Write-Host ""
Write-Host "1) (한 번만) Pipeline 인증 setup:"
Write-Host "   ./.azure/setup-azure-auth-for-pipeline.ps1 -SubscriptionId $SubscriptionId -GithubRepo feone90/stock-insight"
Write-Host ""
Write-Host "2) GitHub variable에 Web App 이름 등록:"
Write-Host "   gh variable set AZURE_WEBAPP_NAME --body '$webAppName' --env $EnvironmentName --repo feone90/stock-insight"
Write-Host "   gh variable set AZURE_RESOURCE_GROUP --body '$AppResourceGroup' --env $EnvironmentName --repo feone90/stock-insight"
Write-Host ""
Write-Host "3) 첫 이미지 push (이후 GitHub Actions가 자동):"
Write-Host "   docker build -t ghcr.io/feone90/stock-insight-backend:latest backend/"
Write-Host "   docker push ghcr.io/feone90/stock-insight-backend:latest"
Write-Host "   az webapp restart --name $webAppName --resource-group $AppResourceGroup"
Write-Host ""
Write-Host "4) 1분 대기 후 alembic 자동 실행 확인 + Universe seed:"
Write-Host "   az webapp ssh --name $webAppName --resource-group $AppResourceGroup"
Write-Host "   # ssh 안에서: python -m scripts.seed_universe"
Write-Host ""
Write-Host "5) /api/health 확인:"
Write-Host "   curl $webAppUrl/api/health"
Write-Host ""
Write-Host "6) Vercel:"
Write-Host "   - NEXT_PUBLIC_API_URL=$webAppUrl 설정 + redeploy"
Write-Host "   - Vercel URL 받은 뒤 CORS_ORIGINS 업데이트:"
Write-Host "   az webapp config appsettings set --name $webAppName --resource-group $AppResourceGroup --settings 'CORS_ORIGINS=[`"https://<vercel-url>`",`"http://localhost:3000`"]'"
