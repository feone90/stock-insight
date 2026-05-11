// CI/CD 파이프라인 전용 인프라 — 별도 RG에 GitHub Actions OIDC용 Managed Identity.
//
// 분리 사유 (Azure pipeline guidance):
//   - 파이프라인 MI는 application MI와 혼동 X. 별도 RG / 별도 lifecycle.
//   - federated credential subject = GitHub repo + environment (branch X)
//   - RBAC (Contributor on app RG)은 cross-RG라 ps1에서 az CLI로 별도 처리.

targetScope = 'resourceGroup'

@minLength(1)
@description('GitHub repository in "owner/name" form (e.g., feone90/stock-insight).')
param githubRepo string

@minLength(1)
@description('Environment name (e.g., dev). Used in federated credential subject.')
param environmentName string

@description('Azure region. Defaults to the pipeline resource group location.')
param location string = resourceGroup().location

var resourceToken = uniqueString(subscription().id, resourceGroup().id, location, environmentName)

resource pipelineIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'azidp${resourceToken}'
  location: location
}

// Federated credential — GitHub Actions OIDC issuer
// subject 형식: repo:<owner>/<name>:environment:<env>
// (Azure pipeline guidance: environment 기반 권장, branch X)
resource fedCredEnvironment 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: pipelineIdentity
  name: 'github-${environmentName}'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepo}:ref:refs/heads/main'
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

output pipelineIdentityName string = pipelineIdentity.name
output pipelineClientId string = pipelineIdentity.properties.clientId
output pipelinePrincipalId string = pipelineIdentity.properties.principalId
