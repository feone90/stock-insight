# 세션 마무리 — 2026-04-30 저녁

다른 PC에서 이어서 개발 가능하도록 정리. 새 PC에서는 이 파일부터 읽어라.

## 0. 환경 setup (다른 PC 처음 시작)

```bash
# 1. 코드 받기
git clone https://github.com/feone90/stock-insight.git
cd stock-insight

# 2. 브랜치 체크아웃 (P3 ontology graph + 캔들/모바일 fix 미머지)
git checkout feat/v2-p3-stock-universe
git pull

# 3. backend deps
cd backend
uv sync --dev   # uv 설치되어 있어야. 없으면 `pip install uv`

# 4. .env 만들기 — 기존 PC .env 복사 또는 .env.example 기반 채움
#    필수 키: DATABASE_URL, LLM_API_KEY/ENDPOINT/DEPLOYMENT/MODEL,
#             DART_API_KEY, FRED_API_KEY, SEC_USER_AGENT
cp .env.example .env
# 그리고 실제 값 입력

# 5. PostgreSQL 17 — 로컬 setup. 빈 DB stockinsight 생성 + alembic 적용
createdb stockinsight    # 또는 pgAdmin GUI
uv run alembic upgrade head

# 6. universe seed (1회)
uv run python -m scripts.seed_universe   # KR 2,556 + US 503

# 7. backend 실행
uv run uvicorn app.main:app --reload --port 8000

# 8. frontend (별도 터미널)
cd ../frontend
npm install
npm run dev   # http://localhost:3000
```

## 1. 머지된 것 (main, commit `30d73ce`, 17 commits)

자세한 timeline은 `~/.claude/projects/.../memory/project_v2_status_2026_04_30_eve.md` 또는 git log.

핵심:
- **P1.7 Universe** — KOSPI 2,556 + S&P 500 503 = 3,052 tier=1.
- **P1.6 v0~v3 ontology** — sector_match (KSIC→GICS bridge로 KR↔US cross-match) + SEC 8-K LLM RAG + News competitor inverse + 가격 corr 검증.
- **8 nightly cron** 06:00~07:00 KST: universe refresh / sector_match / sec_8k / news / fred / inverse_verify.
- **v2 카드** — 7섹션, 한국어 친화 카피, cross-market 우선 정렬.
- **FRED collector** — VIX/US10Y/FedFunds/UNRATE.

## 2. 미머지 branch — `feat/v2-p3-stock-universe` (5 commits ahead)

| commit | 내용 |
|---|---|
| `ae9c0a8` | candlestick 차트 + 한국어 timeFormatter + MA20 정리 + legend |
| `bc7b32e` | 6단계 기간 토글 (10일/30일/60일/3개월/6개월/1년) + US 종목 가격 sync |
| `0c6398f` | P3 ontology graph (`/v2/stock/[ticker]/graph`) — react-force-graph-2d |
| `444bbdc` | 모바일 nav wrap + "분석 다시" 텍스트 hide |
| (next) | (deploy 준비 — Dockerfile uv 기반 + start.sh + CORS) |

## 3. 진행 중 (다른 PC에서 이어서)

### 호스팅 결정 — Vercel(frontend) + Railway(backend+db)

이미 진행한 것:
- `backend/Dockerfile` — uv 기반 multi-stage 빌드 (port $PORT 동적)
- `backend/start.sh` — alembic upgrade → uvicorn (실행권한 chmod +x)
- `app/config.py` — cors_origins 이미 있음. Railway env에서 JSON list 형식으로 override
- `frontend/src/services/api.ts` — `process.env.NEXT_PUBLIC_API_URL` 이미 사용

남은 deploy step:
1. **사용자 가입** (다른 PC에서):
   - https://railway.app GitHub 로그인
   - https://vercel.com GitHub 로그인
2. **Railway 프로젝트 생성**:
   - New Project → Deploy from GitHub → stock-insight repo
   - Root Directory: `backend/`
   - Add Plugin: PostgreSQL
   - Variables (env tab) — `.env`에서 옮김:
     - `DATABASE_URL` = (Railway가 자동 주입)
     - `LLM_API_KEY`, `LLM_ENDPOINT`, `LLM_DEPLOYMENT`, `LLM_MODEL`
     - `DART_API_KEY`, `FRED_API_KEY`, `SEC_USER_AGENT`
     - `CORS_ORIGINS` = `["https://stockinsight-yohan.vercel.app"]` (JSON list)
     - `SCHEDULER_ENABLED=true`
     - `TAVILY_API_KEY` (선택, web_search 분석용)
   - Deploy 시작 — log에 `alembic upgrade head` 성공 + `uvicorn on 0.0.0.0:$PORT` 확인
   - Public URL 활성화 (Settings → Generate Domain) — `https://stockinsight-yohan.up.railway.app` 같은 URL
3. **Vercel 프로젝트 생성**:
   - Import Git Repository → stock-insight
   - Root Directory: `frontend/`
   - Environment Variables: `NEXT_PUBLIC_API_URL=https://stockinsight-yohan.up.railway.app`
   - Deploy
4. **CORS 검증** — Vercel URL이 Railway `CORS_ORIGINS`에 들어있어야 함. 미들웨어 통과 확인.
5. **Universe seed** (Railway shell에서 1회):
   ```bash
   railway run python -m scripts.seed_universe
   railway run python -m scripts.ontology_backfill --source sec --since 2026-01-01 --limit 30
   ```
6. **가족 공유** — Vercel URL 카톡으로.

## 4. 보류 작업 (호스팅 후, 우선순위 순)

| 작업 | 시간 | ROI |
|---|---|---|
| **DART scraper (KR contract)** | 1-2시간 | 중 — KR ontology 강화 |
| **KR PER/PBR source** | 1시간 | 작 — 펀더멘털 1단 보강 |
| **P3 그래프 모바일 polish** | 1-2시간 | 중 — 가족 모바일 사용 시 |
| **매크로/펀더멘털 collector 안정** | 1시간 | 작 |

## 5. 메모리 / 컨텍스트

다음 세션에서 메모리 자동 로드되는 위치 (Windows):
- `C:\Users\장채연(ChaeyeonJang)\.claude\projects\C--code-personal-stock-insight\memory\`
- 핵심 파일: `MEMORY.md`, `project_v2_status_2026_04_30_eve.md`, `project_v2_pivot.md`

**다른 PC에서 메모리 같이 쓰려면**: 해당 폴더를 새 PC에 복사. 또는 그냥 git의 `docs/SESSION_STATUS.md`(이 파일)만 봐도 충분.

## 6. 비밀번호 / 키 (다른 PC에서 새로 입력)

`.env`는 git ignored이라 안 들어감. 다른 PC에서 직접 입력:
- DART_API_KEY: opendart.fss.or.kr (무료, 5분)
- FRED_API_KEY: fred.stlouisfed.org (무료, 1분)
- SEC_USER_AGENT: 이메일 포함 문자열 (e.g. "StockInsight family-use yohan1422@gmail.com")
- LLM_*: Azure OpenAI (기존 PC `.env`에서 복사)
- ADMIN_EMAIL/PASSWORD: 기존 PC .env에서 복사 또는 새 값 설정

## 7. 빠른 sanity test (다른 PC)

```bash
cd backend
uv run python -m pytest tests/ --ignore=tests/integration -m "not smoke"
# 351 passed 기대

# 005930 카드 분석 직접 호출
PYTHONIOENCODING=utf-8 uv run python -c "
from dotenv import load_dotenv; load_dotenv()
import asyncio
from app.services.analyst.engine import analyze
r = asyncio.run(analyze('005930'))
print(r.glance.one_line)
"
# → '주가 흐름은 아직 버티는 모양이지만...' 식 한국어 카피 출력 = 정상
```

문제 시: `memory/project_v2_status_2026_04_30_eve.md`의 "작동 안 하는 것 / 보류" 섹션 참고.
