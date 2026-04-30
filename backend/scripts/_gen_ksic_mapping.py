"""One-shot LLM call to generate KSIC → GICS mapping. Run once, output saved
to app/data/ksic_to_gics.json. Delete after run."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, select

load_dotenv()

from app.database import async_session  # noqa: E402
from app.models import Stock  # noqa: E402
from app.services.llm.adapter import get_adapter  # noqa: E402

GICS_SECTORS = [
    "Energy", "Materials", "Industrials",
    "Consumer Discretionary", "Consumer Staples",
    "Health Care", "Financials",
    "Information Technology", "Communication Services",
    "Utilities", "Real Estate",
]

PROMPT = """한국표준산업분류(KSIC)의 한국어 sector 이름들을 GICS 11 sector 중 가장 적합한 하나에 매핑하라.

KSIC sector list (한국어):
{ksic_json}

GICS 11 sectors:
{gics_list}

응답은 하나의 JSON 객체. 자연어 설명 / 코드펜스 없이:
{{
  "mappings": {{
    "<KSIC 이름 1>": "<GICS sector>",
    "<KSIC 이름 2>": "<GICS sector>"
  }}
}}

규칙:
- 모든 KSIC 항목 빠짐없이 매핑
- GICS sector 값은 위 11개 중 정확한 영문 표기
- 분류 애매하면 가장 가까운 GICS. "Industrials" 또는 "Consumer Discretionary" fallback
"""


async def main() -> None:
    async with async_session() as s:
        rows = (await s.execute(
            select(Stock.sector)
            .where(Stock.market.in_(["KOSPI", "KOSDAQ"]))
            .group_by(Stock.sector)
            .order_by(func.count().desc())
        )).all()
        ksic = [r[0] for r in rows if r[0] and r[0] != "Unknown"]

    prompt = PROMPT.format(
        ksic_json=json.dumps(ksic, ensure_ascii=False, indent=2),
        gics_list="\n".join(f"- {g}" for g in GICS_SECTORS),
    )
    print(f"KSIC count: {len(ksic)}, prompt len: {len(prompt)}")

    raw = await get_adapter().generate_json(prompt)
    print(f"response len: {len(raw)}")
    parsed = json.loads(raw)
    mappings = parsed.get("mappings", {})

    invalid = {k: v for k, v in mappings.items() if v not in GICS_SECTORS}
    missing = set(ksic) - set(mappings.keys())
    print(f"received: {len(mappings)} | invalid GICS: {len(invalid)} | missing KSIC: {len(missing)}")
    if invalid:
        print("invalid sample:", list(invalid.items())[:5])
    if missing:
        print("missing sample:", list(missing)[:5])

    Path("app/data/ksic_to_gics.json").write_text(
        json.dumps(mappings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("saved app/data/ksic_to_gics.json")


if __name__ == "__main__":
    asyncio.run(main())
