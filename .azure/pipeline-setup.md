# Azure 배포 — 처음 한 번 setup

이 가이드는 StockInsight를 Azure App Service + PostgreSQL Flexible Server에 배포하기 위한 1회성 setup. 한 번 끝내면 그 후 `git push origin main`마다 GitHub Actions가 자동으로 build → push → deploy.

## 0. 사전 도구 (사용자 PC)

| 도구 | 확인 명령 | 설치 |
|---|---|---|
| Azure CLI | `az --version` | `winget install Microsoft.AzureCLI` |
| GitHub CLI | `gh --version` | `winget install GitHub.cli` |
| Docker (첫 이미지 push용) | `docker --version` | Docker Desktop |
| Bicep extension | `az bicep version` | `az bicep install` |

`az login` + `gh auth login` 둘 다 완료.

## 1. 사용자 정보 확보

```powershell
# Azure subscription ID (MPN sub)
az account list --output table
# 출력 중 MPN 항목의 SubscriptionId 복사

$SUBSCRIPTION_ID = "여기에-MPN-sub-id"
```

## 2. Secrets 파일 채우기

```powershell
Copy-Item .azure/secrets.env.example .azure/secrets.env
# 에디터에서 .azure/secrets.env 열고 각 값 입력
```

필수:
- `POSTGRES_ADMIN_PASSWORD` — ≥12자 강한 비밀번호
- `GHCR_TOKEN` — github.com/settings/tokens 에서 `read:packages`+`write:packages` scope로 발급
- `LLM_ENDPOINT`, `LLM_API_KEY`, `LLM_DEPLOYMENT` — 기존 `backend/.env`에서 복사
- `JWT_SECRET`, `ADMIN_PASSWORD`

선택 (없으면 빈 값):
- `DART_API_KEY`, `FRED_API_KEY`, `TAVILY_API_KEY`

## 3. 인프라 배포 (App Service + Postgres + App Insights)

```powershell
./.azure/deploy-infra.ps1 -SubscriptionId $SUBSCRIPTION_ID
```

이 스크립트:
1. App resource group 생성 (없으면)
2. `az deployment group what-if`으로 검증 (변경 사항 출력)
3. 사용자 `y` 확인 후 실제 deploy (5–10분)
4. Web App 이름 / URL / Postgres FQDN 출력
5. 다음 step 안내

## 4. CI/CD 파이프라인 인증 setup

```powershell
./.azure/setup-azure-auth-for-pipeline.ps1 -SubscriptionId $SUBSCRIPTION_ID -GithubRepo feone90/stock-insight
```

이 스크립트:
1. Pipeline용 별도 RG (`rg-stockinsight-pipeline`) 생성
2. User-assigned Managed Identity + GitHub OIDC federated credential 생성
3. MI에 App RG Contributor 역할 부여
4. GitHub repo secrets 등록 (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`)
5. GitHub environment `dev` 생성 + `AZURE_RESOURCE_GROUP` var

## 5. Web App 이름을 GitHub var에 등록

step 3의 출력에 있는 web app 이름을:

```powershell
gh variable set AZURE_WEBAPP_NAME --body 'azapp{token}' --env dev --repo feone90/stock-insight
```

## 6. 첫 이미지 push (수동, 1회)

App Service가 처음 시작하려면 이미지가 ghcr.io에 있어야 합니다. 그 후엔 GitHub Actions가 자동.

```powershell
docker build -t ghcr.io/feone90/stock-insight-backend:latest backend/
echo $env:GHCR_TOKEN | docker login ghcr.io -u feone90 --password-stdin
docker push ghcr.io/feone90/stock-insight-backend:latest

az webapp restart --name azapp{token} --resource-group rg-stockinsight-dev
```

## 7. DB 첫 setup (Universe seed)

App Service container 시작 시 `start.sh`가 `alembic upgrade head` 자동 실행 → schema 생성. universe seed는 별도 1회 실행:

```powershell
# 1분 대기 — container 시작 + alembic 완료
Start-Sleep -Seconds 60

# Web App SSH (Azure Portal에서도 가능)
az webapp ssh --name azapp{token} --resource-group rg-stockinsight-dev
# ssh 안에서:
python -m scripts.seed_universe
exit
```

`scripts.seed_universe`는 KOSPI 2,556 + S&P 500 503 = tier=1 3,052 종목 채움.

## 8. Health check

```powershell
curl https://azapp{token}.azurewebsites.net/api/health
# {"status":"ok"}
```

## 9. Vercel frontend 연결

1. https://vercel.com 가입 (GitHub 로그인) → Import `feone90/stock-insight`
2. Root Directory: `frontend/`
3. Environment Variables:
   - `NEXT_PUBLIC_API_URL=https://azapp{token}.azurewebsites.net`
4. Deploy → Vercel이 URL 발급 (예: `https://stock-insight.vercel.app`)
5. Vercel URL을 backend CORS에 추가:

```powershell
$VERCEL_URL = "https://stock-insight.vercel.app"
az webapp config appsettings set `
    --name azapp{token} `
    --resource-group rg-stockinsight-dev `
    --settings "CORS_ORIGINS=[`"$VERCEL_URL`",`"http://localhost:3000`"]"
az webapp restart --name azapp{token} --resource-group rg-stockinsight-dev
```

## 10. 가족 공유

Vercel URL을 카톡으로 공유. 끝.

---

## 그 뒤로

`git push origin main` → `.github/workflows/azure-deploy.yml`이:
1. `backend/Dockerfile` build
2. `ghcr.io/feone90/stock-insight-backend:<sha>` push (+ `:latest`)
3. Azure OIDC login → `az webapp config container set` → restart
4. `/api/health` curl로 검증

1-2분 안에 새 이미지 반영.

## 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `az webapp ssh` 실패 ("Container not ready") | 첫 시작 후 ~1분 대기 필요. 또는 Portal SSH 사용 |
| App Service /api/health 500 | App Service > Log stream으로 stdout 확인. alembic upgrade 실패 가능성 (Postgres firewall, ssl=require 확인) |
| GitHub Actions OIDC 실패 | federated credential subject 일치 확인 (`repo:feone90/stock-insight:environment:dev`). 환경 misspell? |
| Postgres 연결 실패 | App Service > Configuration > DATABASE_URL 확인 (`?ssl=require` 포함). firewall rule "AllowAllAzureServices" 존재 확인 |
| 이미지 pull 실패 | App settings에 `DOCKER_REGISTRY_SERVER_PASSWORD`가 ghcr.io 유효 PAT인지 확인. 만료 시 재발급 후 `az webapp config appsettings set --settings DOCKER_REGISTRY_SERVER_PASSWORD=<new>` |
