// StockInsight 인프라 — Azure App Service (Linux Container) + PostgreSQL Flexible Server.
//
// dev 환경 설계 결정 (plan §4):
//   - Key Vault skip → secrets는 App Service app settings에 직접 (production 진입 시 module 추가)
//   - Service Connector skip → username/password connection string 사용
//   - 단일 env (dev) — staging/prod는 추후 분기
//
// Bicep best practices:
//   - resourceToken = uniqueString(...) per-env 충돌 방지
//   - 모든 리소스 az{prefix}{token} 형식
//   - 최신 API version
//   - User-assigned MI 부착, App Insights env, CORS, diagnostic settings, Linux reserved=true
//   - Postgres v17, Azure Services firewall, user/pass param-only

targetScope = 'resourceGroup'

// ────────────────────────────────────────────────────────────
// Parameters
// ────────────────────────────────────────────────────────────

@minLength(1)
@description('Environment name (e.g., dev). Forms part of resourceToken.')
param environmentName string

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Container image URL (e.g., ghcr.io/owner/repo-backend:latest).')
param containerImage string

@description('GitHub Container Registry username (for private image pull).')
param ghcrUsername string

@secure()
@description('GitHub PAT with read:packages scope (for private image pull).')
param ghcrToken string

@minLength(1)
@description('PostgreSQL administrator login. Cannot be "postgres" / "admin" / "root".')
param postgresAdminLogin string

@minLength(12)
@secure()
@description('PostgreSQL administrator password (≥12 chars, mixed case/digit/symbol).')
param postgresAdminPassword string

@description('List of CORS origins (JSON array param).')
param corsOrigins array = ['http://localhost:3000']

// LLM
@description('Azure OpenAI endpoint URL.')
param llmEndpoint string
@secure()
@description('Azure OpenAI API key.')
param llmApiKey string
@description('Azure OpenAI deployment name.')
param llmDeployment string
@description('Azure OpenAI model name.')
param llmModel string = 'gpt-5'

// Data sources
@secure()
@description('DART API key (KR disclosure). Empty string if unused.')
param dartApiKey string = ''
@secure()
@description('FRED API key (US macro data). Empty string if unused.')
param fredApiKey string = ''
@description('SEC EDGAR User-Agent header (e.g., "StockInsight family-use you@example.com").')
param secUserAgent string
@secure()
@description('Tavily web-search API key. Empty string if unused.')
param tavilyApiKey string = ''

// Misc
@description('PostgreSQL DB name (must not be "postgres").')
param postgresDbName string = 'stockinsight'

@description('JWT signing secret (rotate per env).')
@secure()
param jwtSecret string

@description('Admin email (initial login).')
param adminEmail string
@secure()
@description('Admin password (initial login).')
param adminPassword string

// ────────────────────────────────────────────────────────────
// Computed
// ────────────────────────────────────────────────────────────

var resourceToken = uniqueString(subscription().id, resourceGroup().id, location, environmentName)

// ────────────────────────────────────────────────────────────
// User-assigned Managed Identity (앱용)
// ────────────────────────────────────────────────────────────

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'azida${resourceToken}'
  location: location
}

// ────────────────────────────────────────────────────────────
// Observability: Log Analytics + Application Insights
// ────────────────────────────────────────────────────────────

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'azlog${resourceToken}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'azai${resourceToken}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ────────────────────────────────────────────────────────────
// PostgreSQL Flexible Server (Burstable B1ms, v17)
// ────────────────────────────────────────────────────────────

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'azpsq${resourceToken}'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '17'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      passwordAuth: 'Enabled'
      activeDirectoryAuth: 'Disabled'
    }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Allow Azure services (App Service outbound). Best practice rule.
resource postgresFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ────────────────────────────────────────────────────────────
// App Service Plan (Linux B1)
// ────────────────────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'azasp${resourceToken}'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true // Linux 필수
  }
}

// ────────────────────────────────────────────────────────────
// Web App for Containers
// ────────────────────────────────────────────────────────────

var databaseUrl = 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDbName}?ssl=require'

resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: 'azapp${resourceToken}'
  location: location
  kind: 'app,linux,container'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/api/health'
      cors: {
        allowedOrigins: corsOrigins
        supportCredentials: true
      }
      appSettings: [
        // App Insights (best practice: must inject APPLICATIONINSIGHTS_CONNECTION_STRING)
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        // 컨테이너 registry (ghcr.io)
        {
          name: 'DOCKER_REGISTRY_SERVER_URL'
          value: 'https://ghcr.io'
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_USERNAME'
          value: ghcrUsername
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_PASSWORD'
          value: ghcrToken
        }
        // Container 내부 listen port (start.sh가 $PORT 받음 → uvicorn)
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
        // 시작 시 컨테이너 로그를 stdout으로
        {
          name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE'
          value: 'false'
        }
        // DB
        {
          name: 'DATABASE_URL'
          value: databaseUrl
        }
        // App config (non-secret)
        {
          name: 'CORS_ORIGINS'
          value: string(corsOrigins)
        }
        {
          name: 'SCHEDULER_ENABLED'
          value: 'true'
        }
        {
          name: 'SCHEDULER_TIMEZONE'
          value: 'Asia/Seoul'
        }
        {
          name: 'DEV_MODE'
          value: 'false'
        }
        // LLM (Azure OpenAI)
        {
          name: 'LLM_PROVIDER'
          value: 'azure_openai'
        }
        {
          name: 'LLM_ENDPOINT'
          value: llmEndpoint
        }
        {
          name: 'LLM_API_KEY'
          value: llmApiKey
        }
        {
          name: 'LLM_DEPLOYMENT'
          value: llmDeployment
        }
        {
          name: 'LLM_MODEL'
          value: llmModel
        }
        // 외부 데이터 소스
        {
          name: 'DART_API_KEY'
          value: dartApiKey
        }
        {
          name: 'FRED_API_KEY'
          value: fredApiKey
        }
        {
          name: 'SEC_USER_AGENT'
          value: secUserAgent
        }
        {
          name: 'TAVILY_API_KEY'
          value: tavilyApiKey
        }
        // Auth
        {
          name: 'JWT_SECRET'
          value: jwtSecret
        }
        {
          name: 'ADMIN_EMAIL'
          value: adminEmail
        }
        {
          name: 'ADMIN_PASSWORD'
          value: adminPassword
        }
      ]
    }
  }
  dependsOn: [
    postgresDb
    postgresFirewallAzure
  ]
}

// ────────────────────────────────────────────────────────────
// Diagnostic settings (best practice: must define for App Service + Postgres)
// ────────────────────────────────────────────────────────────

resource webAppDiagnostic 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: webApp
  name: 'webapp-to-log-analytics'
  properties: {
    workspaceId: logWorkspace.id
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
      }
      {
        category: 'AppServicePlatformLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource postgresDiagnostic 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: postgres
  name: 'postgres-to-log-analytics'
  properties: {
    workspaceId: logWorkspace.id
    logs: [
      {
        category: 'PostgreSQLLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ────────────────────────────────────────────────────────────
// Outputs (deploy 직후 사용자가 GitHub vars / Vercel env에 채워야 할 값)
// ────────────────────────────────────────────────────────────

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output webAppHostName string = webApp.properties.defaultHostName
output resourceGroupName string = resourceGroup().name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output postgresDbName string = postgresDb.name
output appIdentityClientId string = appIdentity.properties.clientId
