# GitHub Actions OIDC 인증 setup.
#
# 1회 실행 후 main push마다 자동 deploy.
# Environment 사용 안 함 (admin 권한 불필요) — federated credential은
# main 브랜치 push 시에만 OIDC token 발급.
#
# 작동:
#   1. Pipeline RG 생성
#   2. pipeline.bicep deploy (MI + federated credential — main branch 한정)
#   3. App RG에 Contributor RBAC 부여
#   4. GitHub repo secrets + repo-level variable 등록

param(
    [Parameter(Mandatory=$true)][string]$SubscriptionId,
    [Parameter(Mandatory=$true)][string]$GithubRepo,
    [string]$AppResourceGroup = "rg-stockinsight-dev",
    [string]$PipelineResourceGroup = "rg-stockinsight-pipeline",
    [string]$Location = "koreacentral",
    [string]$EnvironmentName = "dev"
)

$ErrorActionPreference = "Stop"

# ─── subscription ────────────────────────────────────────────
Write-Host "[1/5] Setting subscription..."
az account set --subscription $SubscriptionId
$tenantId = az account show --query tenantId -o tsv

# ─── Pipeline RG ─────────────────────────────────────────────
Write-Host "[2/5] Ensuring pipeline resource group..."
$ErrorActionPreference = "Continue"
$pipeRgShow = az group show --name $PipelineResourceGroup 2>$null
$ErrorActionPreference = "Stop"
if (-not $pipeRgShow) {
    az group create --name $PipelineResourceGroup --location $Location --output none
}

# ─── App RG가 없으면 빈 RG 미리 생성 (RBAC scope 필요) ────────
$ErrorActionPreference = "Continue"
$appRgShow = az group show --name $AppResourceGroup 2>$null
$ErrorActionPreference = "Stop"
if (-not $appRgShow) {
    Write-Host "  App RG '$AppResourceGroup' 미존재 — 빈 RG 미리 생성 (Contributor 역할 부여 위함)..."
    az group create --name $AppResourceGroup --location $Location --output none
}
$appRgId = az group show --name $AppResourceGroup --query id -o tsv

# ─── pipeline.bicep deploy ───────────────────────────────────
Write-Host "[3/5] Deploying pipeline.bicep (in-place update if already exists)..."
$deployResult = az deployment group create `
    --resource-group $PipelineResourceGroup `
    --template-file "infra/pipeline.bicep" `
    --parameters githubRepo=$GithubRepo environmentName=$EnvironmentName `
    --query "properties.outputs" -o json | ConvertFrom-Json

$clientId = $deployResult.pipelineClientId.value
$principalId = $deployResult.pipelinePrincipalId.value

# ─── RBAC: Contributor on App RG ─────────────────────────────
Write-Host "[4/5] Assigning Contributor on $AppResourceGroup..."
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

# ─── GitHub repo secrets + repo-level variable ───────────────
Write-Host "[5/5] Registering GitHub secrets + variable (repo-level, no environment)..."
gh secret set AZURE_CLIENT_ID --body $clientId --repo $GithubRepo
gh secret set AZURE_TENANT_ID --body $tenantId --repo $GithubRepo
gh secret set AZURE_SUBSCRIPTION_ID --body $SubscriptionId --repo $GithubRepo

gh variable set AZURE_RESOURCE_GROUP --body $AppResourceGroup --repo $GithubRepo

Write-Host ""
Write-Host "==============================================="
Write-Host "파이프라인 인증 setup 완료!"
Write-Host "==============================================="
Write-Host "  Pipeline MI client ID: $clientId"
Write-Host "  Tenant ID:             $tenantId"
Write-Host ""
Write-Host "GitHub repo secrets (3개):"
Write-Host "  AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID"
Write-Host ""
Write-Host "GitHub repo-level variable (1개):"
Write-Host "  AZURE_RESOURCE_GROUP=$AppResourceGroup"
Write-Host ""
Write-Host "다음:"
Write-Host "  - main.bicep deploy 후 출력된 web app 이름을 AZURE_WEBAPP_NAME var로 등록:"
Write-Host "    gh variable set AZURE_WEBAPP_NAME --body '<webAppName>' --repo $GithubRepo"
Write-Host "  - git push origin main → workflow 자동 트리거"
