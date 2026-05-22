# YouTube Media Insights Design

Date: 2026-05-22

## Goal

StockInsight에 `미디어 인사이트` 페이지를 추가한다. 사용자가 등록한 YouTube 채널들의 신규 영상을 매번 직접 보지 않아도, 영상에서 실제로 나온 발언을 기반으로 시장 의견을 한눈에 파악하게 하는 기능이다.

이 기능은 뉴스/공시처럼 공식 자료가 아니므로 기존 종목 카드의 종합 판단에 직접 섞지 않는다. 별도 페이지에서 "시장 해설/의견 레이어"로만 제공한다.

## Product Direction

채널 등록 구조는 `관리자 기본 채널 + 사용자 추가 채널`로 한다.

- 관리자 기본 채널: 서비스 품질을 위해 검증된 투자/경제 채널을 공통 제공한다.
- 사용자 추가 채널: 각 사용자가 자주 보는 채널을 추가할 수 있다.
- 분석 결과는 등록 채널 전체를 대상으로 보여주되, 사용자의 즐겨찾기 종목과 매칭되는 영향도 함께 표시한다.

## Page Structure

페이지는 `테마 중심 시장 맵 + 채널별 발언 피드` 조합으로 구성한다.

### 1. 테마 중심 시장 맵

여러 채널에서 반복 언급된 시장 쟁점을 LLM이 묶어 보여준다.

예시:

- AI 인프라 투자 지속
- 금리 재상승 부담
- K-반도체 공급 우위
- 전기차 수요 둔화
- 원전/방산 정책 모멘텀

각 테마는 다음 정보를 가진다.

- 테마명
- 긍정/부정/혼재 톤
- 연결 종목
- 언급 채널 수
- 대표 발언 요약
- 핵심 근거 문장 또는 timestamp
- 신뢰도: 대본 기반인지, 자동자막인지, 수집 실패 후 보류인지

### 2. 종목 영향 큐

테마가 실제 종목에 어떻게 연결되는지 보여준다. 이 영역은 포트폴리오 페이지와 연결성이 있다.

예시:

- `MSFT`: OpenAI/클라우드 CAPEX/AI 계약 회수 시점
- `SK하이닉스`: HBM 공급 제약과 가격 유지
- `삼성전자`: 메모리 회복은 긍정, 파운드리 경쟁력은 확인 필요

카드 판단에는 직접 반영하지 않는다. 대신 "미디어 의견에서 자주 언급되는 영향"으로 표시한다.

### 3. 채널별 발언 피드

각 채널의 최신 영상별로 실제 발언 요약을 보여준다.

표시 항목:

- 채널명
- 영상 제목
- 업로드 시각
- 대본 수집 상태
- 요약
- 핵심 인용 또는 timestamp
- 연결 테마
- 연결 종목
- 의견 톤: 긍정/부정/혼재/중립
- 과장/추측/광고성 가능성 플래그

테마를 클릭하면 해당 테마와 연결된 채널 피드만 필터링한다.

## Data Collection

### Video Discovery

채널 및 신규 영상 감지는 공식 YouTube Data API를 우선 사용한다.

권장 흐름:

1. 채널 URL 또는 handle을 channel id로 정규화한다.
2. `channels.list`의 `contentDetails.relatedPlaylists.uploads`를 사용해 업로드 playlist id를 저장한다.
3. `playlistItems.list`로 최근 업로드 영상을 수집한다.
4. 이미 수집한 `video_id`는 다시 분석하지 않는다.

대안으로 `search.list`에 `channelId`, `publishedAfter`, `type=video`, `order=date`를 사용할 수 있으나 quota 비용이 더 크고 검색 결과 제약이 있으므로 기본 경로로 쓰지 않는다.

### Transcript Extraction

공식 YouTube Data API의 captions endpoint는 caption track 조회/다운로드 기능을 제공하지만, 실제 외부 채널 영상의 대본 다운로드는 OAuth 권한과 소유자 권한 문제가 있어 운영용 기본 경로로 보기 어렵다.

따라서 MVP는 다음 원칙으로 설계한다.

1. `youtube-transcript-api` 같은 transcript extractor를 best-effort로 사용한다.
2. 수동 자막이 있으면 수동 자막을 우선한다.
3. 수동 자막이 없으면 자동 생성 자막을 사용한다.
4. 한국어 자막이 있으면 한국어를 우선한다.
5. 영어 자막만 있으면 원문을 저장하고 분석 결과는 한국어로 생성한다.
6. 자막이 없거나 extractor가 실패하면 분석하지 않고 `대본 없음` 또는 `수집 실패`로 표시한다.

제목/설명만으로 영상 내용을 분석하지 않는다. 이 기능의 목적은 "영상에서 실제로 나눈 말"을 기반으로 인사이트를 만드는 것이므로, 제목/설명만 사용하면 추측 분석이 섞일 수 있다.

### Reliability Notes

`youtube-transcript-api`는 공식 YouTube API가 아니라 YouTube 웹 클라이언트의 비공식 경로를 사용하는 방식이다. 운영 환경에서는 다음 실패가 가능하다.

- YouTube가 웹 클라이언트 구조를 바꿔 extractor가 깨짐
- Azure 등 클라우드 IP에서 429 또는 block 발생
- 라이브/프리미어 직후 자동자막이 아직 생성되지 않음
- 채널 또는 영상 단위로 자막 비활성
- 자동자막 품질 저하

따라서 transcript 수집은 실패 가능한 단계로 모델링하고, 재시도/상태/캐싱을 명시적으로 둔다.

## Storage Model

권장 테이블:

- `youtube_channels`
  - `id`
  - `channel_id`
  - `handle`
  - `title`
  - `source_scope`: `admin_default` 또는 `user_added`
  - `user_id`: 사용자 추가 채널인 경우
  - `uploads_playlist_id`
  - `enabled`
  - `last_checked_at`

- `youtube_videos`
  - `id`
  - `channel_id`
  - `video_id`
  - `title`
  - `description`
  - `published_at`
  - `url`
  - `thumbnail_url`
  - `duration`
  - `collected_at`
  - unique `video_id`

- `youtube_transcripts`
  - `id`
  - `video_id`
  - `language_code`
  - `is_generated`
  - `source`: `manual_caption`, `auto_caption`, `extractor`
  - `status`: `ready`, `missing`, `failed`
  - `text`
  - `segments_json`: timestamp segment list
  - `text_hash`
  - `error`
  - `fetched_at`

- `youtube_video_analyses`
  - `id`
  - `video_id`
  - `transcript_id`
  - `summary_ko`
  - `themes_json`
  - `mentioned_stocks_json`
  - `stance`
  - `important_quotes_json`
  - `risk_flags_json`
  - `model`
  - `prompt_version`
  - `created_at`

- `youtube_theme_clusters`
  - `id`
  - `cluster_date`
  - `theme`
  - `tone`
  - `summary_ko`
  - `related_tickers_json`
  - `video_ids_json`
  - `channel_count`
  - `created_at`

## Analysis Flow

1. Scheduled job checks enabled channels for new videos.
2. New `video_id` rows are inserted.
3. Transcript extraction runs once per new video.
4. If transcript is ready, LLM creates a Korean analysis.
5. Daily or on-demand clustering groups video analyses into themes.
6. Frontend reads:
   - latest theme clusters
   - latest channel/video analyses
   - stock impact matches

Re-analysis policy:

- Same transcript hash: do not re-run LLM.
- Prompt version changed: allow manual re-analysis.
- Transcript was previously missing: retry later, especially for newly uploaded videos.
- Transcript failed due 429/block: retry with backoff, do not keep hammering.

## LLM Output Contract

Video-level analysis should return structured JSON:

```json
{
  "summary_ko": "영상 전체 핵심 요약",
  "claims": [
    {
      "claim": "핵심 주장",
      "tone": "positive | negative | mixed | neutral",
      "theme": "테마명",
      "related_tickers": ["MSFT", "NVDA"],
      "evidence_quote": "짧은 근거 문장",
      "timestamp_start": 123.4,
      "confidence": "high | medium | low"
    }
  ],
  "risk_flags": ["speculation", "promotion", "rumor"]
}
```

Rules:

- 한국어 사용자용이므로 요약/테마/주장 표현은 한국어로 만든다.
- 영어 발언은 한국어로 요약하되, 핵심 인용은 원문 또는 번역문 중 UI 정책에 맞게 표시한다.
- 특정 종목 매매 추천처럼 보이는 문장은 피하고 "채널 의견"임을 명확히 한다.
- 뉴스/공시처럼 검증된 사실로 표현하지 않는다.

## API Shape

초기 API 후보:

- `GET /api/youtube/channels`
- `POST /api/youtube/channels`
- `PATCH /api/youtube/channels/{id}`
- `POST /api/youtube/sync`
- `POST /api/youtube/videos/{video_id}/extract`
- `GET /api/youtube/insights?days=7`
- `GET /api/youtube/themes?days=7`
- `GET /api/youtube/videos?channel_id=&theme=&days=`

## UI States

필수 상태:

- 채널 등록 전 empty state
- 신규 영상 감지됨, 대본 추출 대기
- 대본 없음
- 대본 수집 실패
- 분석 완료
- 분석 보류
- YouTube API quota 또는 extractor block 경고

## Out of Scope for MVP

- 댓글 분석
- 좋아요/조회수 기반 채널 영향력 점수
- 영상 다운로드 또는 음성 자체 ASR
- 카드 종합판단에 자동 반영
- 매매 추천 생성
- YouTube 계정 OAuth 기반 개인 구독 목록 가져오기

## MVP Success Criteria

- 사용자가 채널 URL을 등록할 수 있다.
- 등록 채널의 신규 영상이 수집된다.
- 대본이 있는 영상은 텍스트 추출 후 저장된다.
- 대본 기반 영상 요약이 한국어로 생성된다.
- 페이지에서 테마 중심 시장 맵과 채널별 발언 피드를 함께 볼 수 있다.
- 각 인사이트가 어떤 영상/채널/발언에서 나온 것인지 추적 가능하다.
- 대본 수집 실패가 UI에 숨겨지지 않는다.

## References

- YouTube Data API `captions.list`: https://developers.google.cn/youtube/v3/docs/captions/list?hl=en
- YouTube Data API sample requests: https://developers.google.com/youtube/v3/sample_requests
- YouTube Data API `search.list`: https://developers.google.com/youtube/v3/docs/search/list
- `youtube-transcript-api` PyPI: https://pypi.org/project/youtube-transcript-api/
- `youtube-transcript-api` GitHub: https://github.com/jdepoix/youtube-transcript-api

