# StockInsight Azure 인프라 배포 스크립트.
#
# 사전:
#   - az login 완료
#   - backend/.env 작성 (LLM_* / DART / FRED / TAVILY / JWT / ADMIN / SEC_USER_AGENT)
#   - .azure/secrets.env 작성 (POSTGRES_ADMIN_PASSWORD / GHCR_TOKEN — 2개만)
#
# 작동:
#   1. backend/.env + .azure/secrets.env union 로드
#   2. App RG 생성 (idempotent)
#   3. what-if 검증 (사용자 y 확인)
#   4. main.bicep deploy
#   5. 다음 step 안내
#
# Idempotent — 다시 돌려도 안전 (Bicep declarative).

param(
    [Parameter(Mandatory=$true)][string]$SubscriptionId,
    [string]$AppResourceGroup = "rg-stockinsight-dev",
    [string]$Location = "koreacentral",
    [string]$EnvironmentName = "dev"
)

$ErrorActionPreference = "Stop"

# ─── 헬퍼: dotenv 형식 파일 로드 ──────────────────────────────
function Read-EnvFile([string]$path) {
    $result = @{}
    if (-not (Test-Path $path)) { return $result }
    Get-Content $path | ForEach-Object {
        if ($_ -match "^([^=#]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($val -match '^"(.*)"$' -or $val -match "^'(.*)'$") {
                $val = $Matches[1]
            }
            $result[$key] = $val
        }
    }
    return $result
}

# ─── backend/.env + secrets.env union ───────────────────────
$backendEnvFile = "backend/.env"
$secretsFile = ".azure/secrets.env"

if (-not (Test-Path $backendEnvFile)) {
    Write-Error "Missing $backendEnvFile. backend/.env에 LLM_ENDPOINT / LLM_API_KEY / LLM_DEPLOYMENT 등 설정 필요."
    exit 1
}
if (-not (Test-Path $secretsFile)) {
    Write-Error "Missing $secretsFile. Copy from .azure/secrets.env.example and fill in 2 values (POSTGRES_ADMIN_PASSWORD, GHCR_TOKEN)."
    exit 1
}

$config = @{}
(Read-EnvFile $backendEnvFile).GetEnumerator() | ForEach-Object { $config[$_.Key] = $_.Value }
# secrets.env가 backend/.env를 override 가능 (둘 다 있으면 secrets.env 우선)
(Read-EnvFile $secretsFile).GetEnumerator() | ForEach-Object { $config[$_.Key] = $_.Value }

# ─── 필수 값 검증 ────────────────────────────────────────────
$required = @(
    @{ Key = "POSTGRES_ADMIN_PASSWORD"; Source = $secretsFile },
    @{ Key = "GHCR_TOKEN"; Source = $secretsFile },
    @{ Key = "LLM_ENDPOINT"; Source = $backendEnvFile },
    @{ Key = "LLM_API_KEY"; Source = $backendEnvFile },
    @{ Key = "LLM_DEPLOYMENT"; Source = $backendEnvFile },
    @{ Key = "JWT_SECRET"; Source = $backendEnvFile },
    @{ Key = "ADMIN_PASSWORD"; Source = $backendEnvFile }
)
$missing = @()
foreach ($r in $required) {
    if (-not $config.ContainsKey($r.Key) -or [string]::IsNullOrWhiteSpace($config[$r.Key])) {
        $missing += "$($r.Key) (in $($r.Source))"
    }
}
if ($missing.Count -gt 0) {
    Write-Host "Missing required values:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

# 빈 값 default (Bicep optional params)
foreach ($k in @("DART_API_KEY", "FRED_API_KEY", "TAVILY_API_KEY", "LLM_MODEL")) {
    if (-not $config.ContainsKey($k)) { $config[$k] = "" }
}
if (-not $config.ContainsKey("SEC_USER_AGENT") -or [string]::IsNullOrWhiteSpace($config["SEC_USER_AGENT"])) {
    $config["SEC_USER_AGENT"] = "StockInsight family-use yohan1422@gmail.com"
}
if (-not $config.ContainsKey("ADMIN_EMAIL") -or [string]::IsNullOrWhiteSpace($config["ADMIN_EMAIL"])) {
    $config["ADMIN_EMAIL"] = "admin@stockinsight.local"
}

Write-Host "Loaded values:"
Write-Host "  backend/.env       : LLM/DART/FRED/TAVILY/JWT/ADMIN/SEC_USER_AGENT"
Write-Host "  .azure/secrets.env : POSTGRES_ADMIN_PASSWORD, GHCR_TOKEN"
Write-Host "  LLM_ENDPOINT       : $($config.LLM_ENDPOINT.Substring(0, [Math]::Min(40, $config.LLM_ENDPOINT.Length)))..."
Write-Host "  LLM_DEPLOYMENT     : $($config.LLM_DEPLOYMENT)"
Write-Host ""

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

# ─── deploy params 구성 ──────────────────────────────────────
$secretParams = @(
    "postgresAdminPassword=$($config.POSTGRES_ADMIN_PASSWORD)",
    "ghcrToken=$($config.GHCR_TOKEN)",
    "llmEndpoint=$($config.LLM_ENDPOINT)",
    "llmApiKey=$($config.LLM_API_KEY)",
    "llmDeployment=$($config.LLM_DEPLOYMENT)",
    "dartApiKey=$($config.DART_API_KEY)",
    "fredApiKey=$($config.FRED_API_KEY)",
    "tavilyApiKey=$($config.TAVILY_API_KEY)",
    "secUserAgent=$($config.SEC_USER_AGENT)",
    "adminEmail=$($config.ADMIN_EMAIL)",
    "jwtSecret=$($config.JWT_SECRET)",
    "adminPassword=$($config.ADMIN_PASSWORD)"
)
if (-not [string]::IsNullOrWhiteSpace($config.LLM_MODEL)) {
    $secretParams += "llmModel=$($config.LLM_MODEL)"
}

# ─── what-if 검증 ────────────────────────────────────────────
Write-Host "[3/4] Running what-if validation..."
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
Write-Host "2) GitHub variable에 Web App 이름 등록 (AZURE_RESOURCE_GROUP은 setup ps1이 자동 등록):"
Write-Host "   gh variable set AZURE_WEBAPP_NAME --body '$webAppName' --repo feone90/stock-insight"
Write-Host ""
Write-Host "3) 첫 이미지 push (이후 GitHub Actions가 자동):"
Write-Host "   docker build -t ghcr.io/feone90/stock-insight-backend:latest backend/"
Write-Host "   `$env:GHCR_TOKEN | docker login ghcr.io -u feone90 --password-stdin"
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
