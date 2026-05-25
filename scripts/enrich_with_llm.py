"""
3단계 — LLM 한국어 요약·시사점 생성

deduped_news.json 을 읽어 상위 N개 항목에 한국어 요약(`summary_ko`)과
시사점(`insight_ko`) 필드를 추가합니다.

비용 관리:
- 최상위 점수 항목 N개에만 LLM 호출 (기본 N=40)
- 환경변수 ENRICH_TOP_N 으로 조정 가능
- 환경변수 ENRICH_MAX_PER_RUN 으로 1회 호출 수 상한
- 결과는 data/enriched_news.json 으로 저장
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm_json, detect_backend


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "deduped_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
KST = timezone(timedelta(hours=9))

# 상위 몇 개에만 LLM 호출할지
TOP_N = int(os.environ.get("ENRICH_TOP_N", "40"))
MAX_PER_RUN = int(os.environ.get("ENRICH_MAX_PER_RUN", "40"))


PROMPT_TEMPLATE = """당신은 한국의 전략·기획·AI 업무 담당자를 위한 뉴스 큐레이터입니다.

다음 영문/국문 뉴스를 분석하여 JSON으로 응답하세요.

[뉴스 정보]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}
관련 뉴스 수: {related_count}

[응답 형식 — JSON만, 다른 텍스트 없이]
{{
  "summary_ko": "2~3문장. 핵심 사실 전달. 단정적 어조 지양.",
  "insight_ko": "1~2문장. 한국 전략·기획·AI 업무 담당자가 본인 업무에 어떻게 적용할 수 있는지 액션 가능한 시사점."
}}

규칙:
- 한국어로만 응답
- summary_ko: 사실 위주, 80~150자
- insight_ko: '시사점:' 같은 접두어 없이 본문만, 60~120자
- JSON 외 다른 설명·인삿말 절대 금지
"""


def enrich_item(item: dict) -> dict:
    """단일 항목에 한국어 요약·시사점 추가"""
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        date=item.get("date", "")[:10],
        summary=item.get("summary", "")[:400],
        categories=", ".join(item.get("categories", [])),
        related_count=item.get("related_count", 0),
    )
    result = call_llm_json(prompt, max_tokens=400, temperature=0.3)
    if isinstance(result, dict):
        if "summary_ko" in result:
            item["summary_ko"] = result["summary_ko"].strip()
        if "insight_ko" in result:
            item["insight_ko"] = result["insight_ko"].strip()
        item["llm_enriched"] = True
    return item


def main():
    print(f"[start] enrich_with_llm @ {datetime.now(KST).isoformat()}", flush=True)

    backend = detect_backend()
    if backend == "none":
        print("  [warn] No LLM backend available. Skipping enrichment.", flush=True)
        # 입력을 그대로 출력으로 복사
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["enriched_at"] = datetime.now(KST).isoformat()
        data["llm_backend"] = "none"
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]

    # 기존 enriched 결과가 있다면 캐시로 사용 (URL 기준)
    existing_cache = {}
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev = json.load(f)
                for it in prev.get("items", []):
                    if it.get("llm_enriched"):
                        existing_cache[it["url"]] = {
                            "summary_ko": it.get("summary_ko"),
                            "insight_ko": it.get("insight_ko"),
                        }
        except Exception:
            pass

    # 캐시 적용
    cached_count = 0
    for it in items:
        if it["url"] in existing_cache:
            cache = existing_cache[it["url"]]
            if cache.get("summary_ko"):
                it["summary_ko"] = cache["summary_ko"]
                it["insight_ko"] = cache["insight_ko"]
                it["llm_enriched"] = True
                cached_count += 1

    # 상위 N개 중 아직 enrich 안 된 항목만 호출
    need_enrich = [it for it in items[:TOP_N] if not it.get("llm_enriched")]
    print(f"  cached: {cached_count}, need enrich: {len(need_enrich)}", flush=True)

    enriched_count = 0
    # 부분 결과를 매 5건마다 저장
    def save_partial():
        data["enriched_at"] = datetime.now(KST).isoformat()
        data["llm_backend"] = backend
        data["enriched_count_this_run"] = enriched_count
        data["enriched_total"] = sum(1 for it in items if it.get("llm_enriched"))
        data["items"] = items
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # 호출 전에 일단 한 번 저장 (중간 실패 대비)
    save_partial()

    for i, it in enumerate(need_enrich[:MAX_PER_RUN]):
        print(f"  [{i+1}/{min(len(need_enrich), MAX_PER_RUN)}] {it['title'][:60]}", flush=True)
        enrich_item(it)
        enriched_count += 1
        time.sleep(0.5)  # rate-limit
        if enriched_count % 5 == 0:
            save_partial()

    save_partial()
    print(f"[done] enriched +{enriched_count} (total {data['enriched_total']}/{len(items)})", flush=True)


if __name__ == "__main__":
    main()
