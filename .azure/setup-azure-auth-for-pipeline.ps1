# GitHub Actions OIDC 인증 setup.
#
# 1회 실행 후 main push마다 자동 deploy.
#
# 작동:
#   1. Pipeline RG 생성
#   2. pipeline.bicep deploy (MI + federated credential)
#   3. App RG에 Contributor RBAC 부여
#   4. GitHub repo secrets / vars / env 등록

param(
    [Parameter(Mandatory=$true)][string]$SubscriptionId,
    [Parameter(Mandatory=$true)][string]$GithubRepo,  # "owner/name"
    [string]$AppResourceGroup = "rg-stockinsight-dev",
    [string]$PipelineResourceGroup = "rg-stockinsight-pipeline",
    [string]$Location = "koreacentral",
    [string]$EnvironmentName = "dev"
)

$ErrorActionPreference = "Stop"

# ─── subscription ────────────────────────────────────────────
Write-Host "[1/6] Setting subscription..."
az account set --subscription $SubscriptionId
$tenantId = az account show --query tenantId -o tsv

# ─── Pipeline RG ─────────────────────────────────────────────
Write-Host "[2/6] Ensuring pipeline resource group..."
$ErrorActionPreference = "Continue"
$pipeRgShow = az group show --name $PipelineResourceGroup 2>$null
$ErrorActionPreference = "Stop"
if (-not $pipeRgShow) {
    az group create --name $PipelineResourceGroup --location $Location --output none
}

# ─── App RG가 없으면 빈 RG 만 미리 (RBAC scope 필요) ─────────
$ErrorActionPreference = "Continue"
$appRgShow = az group show --name $AppResourceGroup 2>$null
$ErrorActionPreference = "Stop"
if (-not $appRgShow) {
    Write-Host "  App RG '$AppResourceGroup' 미존재 — 빈 RG 미리 생성 (Contributor 역할 부여 위함)..."
    az group create --name $AppResourceGroup --location $Location --output none
}
$appRgId = az group show --name $AppResourceGroup --query id -o tsv

# ─── pipeline.bicep deploy ───────────────────────────────────
Write-Host "[3/6] Deploying pipeline.bicep..."
$deployResult = az deployment group create `
    --resource-group $PipelineResourceGroup `
    --template-file "infra/pipeline.bicep" `
    --parameters githubRepo=$GithubRepo environmentName=$EnvironmentName `
    --query "properties.outputs" -o json | ConvertFrom-Json

$clientId = $deployResult.pipelineClientId.value
$principalId = $deployResult.pipelinePrincipalId.value

# ─── RBAC: Contributor on App RG ─────────────────────────────
Write-Host "[4/6] Assigning Contributor on $AppResourceGroup..."
$ErrorActionPreference = "Continue"
$existing = az role assignment list --assignee $principalId --scope $appRgId --query "[?roleDefinitionName=='Contributor'].id" -o tsv 2>$null
$ErrorActionPreference = "Stop"
if (-not $existing) {
    # Eventual consistency — MI 생성 직후 RBAC 적용 시 가끔 fail. retry.
    for ($i = 1; $i -le 5; $i++) {
        $ErrorActionPreference = "Continue"
        az role assignment create `
            --assignee-object-id $principalId `
            --assignee-principal-type ServicePrincipal `
            --role Contributor `
            --scope $appRgId `
            --output none 2>$null
        $ErrorActionPreference = "Stop"
        Start-Sleep -Seconds 5
        $check = az role assignment list --assignee $principalId --scope $appRgId --query "[?roleDefinitionName=='Contributor'].id" -o tsv 2>$null
        if ($check) { break }
        Write-Host "  retry $i/5 ..."
    }
}

# ─── GitHub secrets ──────────────────────────────────────────
Write-Host "[5/6] Registering GitHub secrets (repo-level)..."
gh secret set AZURE_CLIENT_ID --body $clientId --repo $GithubRepo
gh secret set AZURE_TENANT_ID --body $tenantId --repo $GithubRepo
gh secret set AZURE_SUBSCRIPTION_ID --body $SubscriptionId --repo $GithubRepo

# ─── GitHub environment + vars ───────────────────────────────
Write-Host "[6/6] Creating GitHub environment '$EnvironmentName' + variables..."
gh api --method PUT "repos/$GithubRepo/environments/$EnvironmentName" -f "wait_timer=0" --silent 2>$null | Out-Null

gh variable set AZURE_RESOURCE_GROUP --body $AppResourceGroup --env $EnvironmentName --repo $GithubRepo

# AZURE_WEBAPP_NAME 은 main.bicep deploy 후 별도 등록 (deploy-infra.ps1 출력에 안내됨)

Write-Host ""
Write-Host "==============================================="
Write-Host "파이프라인 인증 setup 완료!"
Write-Host "==============================================="
Write-Host "  Pipeline MI client ID: $clientId"
Write-Host "  Tenant ID:             $tenantId"
Write-Host ""
Write-Host "GitHub repo secrets 등록:"
Write-Host "  AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID"
Write-Host ""
Write-Host "GitHub environment '$EnvironmentName' 생성 + var:"
Write-Host "  AZURE_RESOURCE_GROUP=$AppResourceGroup"
Write-Host ""
Write-Host "다음:"
Write-Host "  - main.bicep deploy 후 출력된 web app 이름을 AZURE_WEBAPP_NAME var로 등록"
Write-Host "  - git push origin main → workflow 자동 트리거"
