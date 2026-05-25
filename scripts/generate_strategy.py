"""
4단계 — 매일 전략 카드 자동 갱신

enriched_news.json 의 상위 항목들을 LLM에 전달하여
오늘자 전략·기획 시사점 카드 5~7개를 자동 생성합니다.

생성된 결과는 data/news.json 의 `strategy` 필드로 저장되어
프론트엔드에서 바로 표시됩니다.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm_json, detect_backend


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "news.json")
KST = timezone(timedelta(hours=9))

# 전략 생성에 사용할 상위 항목 수
TOP_FOR_STRATEGY = 30


PROMPT_TEMPLATE = """당신은 한국의 시니어 전략 컨설턴트입니다. 사용자는 전략·기획과 AI 업무를 함께 수행하는 실무자입니다.

오늘({today}) 수집된 최신 AI·리걸테크·논문 뉴스 상위 {n}개를 아래에 제시합니다 (각 항목 앞 번호가 인덱스).

[뉴스 목록]
{news_blob}

위 흐름을 종합하여 **오늘의 전략·기획 시사점 카드 5~7개**를 작성하세요.

[응답 형식 — JSON 배열만]
[
  {{
    "tag": "TREND 01 · [한 줄 주제]",
    "title": "[20자 이내 헤드라인]",
    "body": "[2~3문장. 흐름 + 근거 + 의미. 단정적 어조 지양.]",
    "action": "[1~2문장. 사용자가 본인 업무에 바로 시도해볼 수 있는 액션. '시사점:' 같은 접두어 없이.]",
    "sources": [번호1, 번호2, ...]
  }},
  ...
]

규칙:
- 한국어
- 각 카드는 서로 다른 관점/주제로 (중복 금지)
- 가능한 한 오늘/이번주 뉴스의 구체적 사실(회사명·금액·날짜)을 근거로 활용
- 일반론 금지, 실무자가 행동할 수 있는 디테일 포함
- 5~7개 사이
- **각 카드의 `sources`는 body·action 작성에 실제로 근거가 된 뉴스 인덱스만 (1~3개 권장, 최대 5개)**
- JSON 배열 외 다른 텍스트 절대 금지
"""


def main():
    print(f"[start] generate_strategy @ {datetime.now(KST).isoformat()}", flush=True)

    # enriched가 없으면 deduped 폴백
    input_path = INPUT_PATH
    if not os.path.exists(INPUT_PATH):
        fallback = os.path.join(ROOT_DIR, "data", "deduped_news.json")
        if os.path.exists(fallback):
            print(f"  [warn] {INPUT_PATH} not found, using {fallback}", flush=True)
            input_path = fallback
        else:
            print(f"  [error] no input file found", flush=True)
            return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    backend = detect_backend()

    # 기존 news.json 의 전략 카드를 보존 (LLM 실패 시 폴백)
    fallback_strategy = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev = json.load(f)
                fallback_strategy = prev.get("strategy", [])
        except Exception:
            pass

    strategy_cards = []

    if backend != "none":
        # 상위 항목으로 프롬프트 구성
        top_items = items[:TOP_FOR_STRATEGY]
        news_lines = []
        for i, it in enumerate(top_items, 1):
            summary = it.get("summary_ko") or it.get("summary", "")[:200]
            news_lines.append(
                f"{i}. [{it.get('source', '?')}, {it.get('date', '')[:10]}] "
                f"{it.get('title', '')[:120]}\n   요약: {summary[:200]}"
            )
        news_blob = "\n".join(news_lines)

        prompt = PROMPT_TEMPLATE.format(
            today=datetime.now(KST).strftime("%Y-%m-%d (%a)"),
            n=len(top_items),
            news_blob=news_blob,
        )

        result = call_llm_json(prompt, max_tokens=2500, temperature=0.4)

        # 응답이 리스트인지 확인
        if isinstance(result, list) and len(result) > 0:
            strategy_cards = []
            for c in result:
                if isinstance(c, dict) and all(k in c for k in ("tag", "title", "body", "action")):
                    # sources 인덱스 → 실제 항목 정보로 변환
                    cited = []
                    raw_sources = c.get("sources") or []
                    if isinstance(raw_sources, list):
                        for idx in raw_sources[:5]:
                            try:
                                i = int(idx) - 1  # 1-based → 0-based
                                if 0 <= i < len(top_items):
                                    ref = top_items[i]
                                    cited.append({
                                        "title": ref.get("title", "")[:140],
                                        "url": ref.get("url", ""),
                                        "source": ref.get("source", ""),
                                        "date": ref.get("date", "")[:10],
                                    })
                            except (ValueError, TypeError):
                                continue
                    strategy_cards.append({
                        "tag": str(c["tag"]).strip(),
                        "title": str(c["title"]).strip(),
                        "body": str(c["body"]).strip(),
                        "action": str(c["action"]).strip(),
                        "citations": cited,
                    })
            print(f"  generated {len(strategy_cards)} cards (avg citations: {sum(len(c['citations']) for c in strategy_cards) / max(1, len(strategy_cards)):.1f})", flush=True)
        else:
            print(f"  [warn] LLM did not return a list: {type(result)}", flush=True)

    if not strategy_cards:
        print("  using fallback strategy cards", flush=True)
        strategy_cards = fallback_strategy

    # 최종 news.json 작성
    payload = {
        "last_updated": datetime.now(KST).isoformat(),
        "build_count": (data.get("build_count", 0) or 0) + 1,
        "llm_backend": backend,
        "sources": data.get("sources", []),
        "items": items,
        "strategy": strategy_cards,
        "stats": {
            "total_items": len(items),
            "enriched_items": sum(1 for it in items if it.get("llm_enriched")),
            "with_related": sum(1 for it in items if it.get("related_count", 0) > 0),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {OUTPUT_PATH} ({len(strategy_cards)} cards, {len(items)} items)", flush=True)


if __name__ == "__main__":
    main()
