"""
3단계 — LLM 한국어 요약·시사점 생성 (v2.1)

deduped_news.json 을 읽어 **영문 항목 전부** + **상위 시사점 후보**에
한국어 요약·시사점을 추가합니다.

전략:
- 영문(lang=en) 항목 → 한국어 요약 필수, 시사점은 score >= 65일 때만
- 한국어(lang=ko) 항목 → 한국어 요약 불필요 (원문이 이미 한국어), 시사점만 score >= 70일 때 추가
- 캐시: 기존 enriched_news.json 의 항목은 URL 기준으로 재사용
- 부분 저장: 매 10건마다 저장
- 비용 제어: ENRICH_MAX_PER_RUN 환경변수로 1회 호출 수 상한

결과는 data/enriched_news.json 으로 저장
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

# 1회 실행에서 최대 호출 수
MAX_PER_RUN = int(os.environ.get("ENRICH_MAX_PER_RUN", "300"))

# 시사점은 일정 점수 이상만
INSIGHT_THRESHOLD_EN = int(os.environ.get("INSIGHT_THRESHOLD_EN", "65"))
INSIGHT_THRESHOLD_KO = int(os.environ.get("INSIGHT_THRESHOLD_KO", "70"))


PROMPT_SUMMARY_ONLY = """다음 영문 뉴스를 한국어로 요약해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "summary_ko": "2~3문장. 핵심 사실. 80~150자. 단정 어조 지양."
}}
"""

PROMPT_WITH_INSIGHT = """다음 뉴스를 한국 전략·기획·AI 업무 담당자 관점에서 분석해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "summary_ko": "2~3문장. 핵심 사실. 80~150자. 영문이면 한국어로 번역·요약. 한국어면 본 요약을 다듬어서.",
  "insight_ko": "1~2문장. 본인 업무에 적용할 액션 가능한 시사점. 60~120자. '시사점:' 같은 접두어 없이 본문만."
}}
"""

PROMPT_KO_INSIGHT_ONLY = """다음 한국어 뉴스에 대한 전략·기획·AI 업무 시사점만 작성해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "insight_ko": "1~2문장. 본인 업무에 적용할 액션 가능한 시사점. 60~120자."
}}
"""


def enrich_item(item: dict) -> dict:
    """단일 항목 enrichment.

    분기:
    - 영문 + 점수>=threshold: summary + insight 같이
    - 영문 + 점수<threshold: summary만
    - 한국어 + 점수>=threshold: insight만
    - 한국어 + 점수<threshold: skip
    """
    lang = item.get("lang", "en")
    score = item.get("score", 0)
    title = item.get("title", "")
    source = item.get("source", "")
    date = item.get("date", "")[:10]
    summary = item.get("summary", "")[:400]
    categories = ", ".join(item.get("categories", []))

    if lang == "en":
        if score >= INSIGHT_THRESHOLD_EN:
            prompt = PROMPT_WITH_INSIGHT.format(
                title=title, source=source, date=date,
                summary=summary, categories=categories,
            )
        else:
            prompt = PROMPT_SUMMARY_ONLY.format(
                title=title, source=source, date=date, summary=summary,
            )
        result = call_llm_json(prompt, max_tokens=400, temperature=0.3)
        if isinstance(result, dict):
            if "summary_ko" in result:
                item["summary_ko"] = result["summary_ko"].strip()
            if "insight_ko" in result:
                item["insight_ko"] = result["insight_ko"].strip()
            item["llm_enriched"] = True

    elif lang == "ko":
        if score >= INSIGHT_THRESHOLD_KO:
            prompt = PROMPT_KO_INSIGHT_ONLY.format(
                title=title, source=source, date=date,
                summary=summary, categories=categories,
            )
            result = call_llm_json(prompt, max_tokens=300, temperature=0.3)
            if isinstance(result, dict) and "insight_ko" in result:
                item["insight_ko"] = result["insight_ko"].strip()
                item["llm_enriched"] = True

    return item


def needs_enrich(item: dict) -> bool:
    """이 항목이 enrich 대상인지 판단"""
    lang = item.get("lang", "en")
    score = item.get("score", 0)

    if lang == "en":
        # 영문은 summary가 필수 → 항상 enrich 대상
        return not item.get("llm_enriched")
    elif lang == "ko":
        # 한국어는 insight가 있을 가치 있는 경우만
        if score >= INSIGHT_THRESHOLD_KO and not item.get("insight_ko"):
            return True
        return False
    return False


def main():
    print(f"[start] enrich_with_llm @ {datetime.now(KST).isoformat()}", flush=True)

    backend = detect_backend()
    if backend == "none":
        print("  [warn] No LLM backend available. Skipping enrichment.", flush=True)
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

    # 캐시 적용
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

    cached_count = 0
    for it in items:
        if it["url"] in existing_cache:
            cache = existing_cache[it["url"]]
            if cache.get("summary_ko"):
                it["summary_ko"] = cache["summary_ko"]
            if cache.get("insight_ko"):
                it["insight_ko"] = cache["insight_ko"]
            if cache.get("summary_ko") or cache.get("insight_ko"):
                it["llm_enriched"] = True
                cached_count += 1

    need_list = [it for it in items if needs_enrich(it)]
    print(f"  cached: {cached_count}, need enrich: {len(need_list)} (max per run: {MAX_PER_RUN})", flush=True)

    def save_partial():
        data["enriched_at"] = datetime.now(KST).isoformat()
        data["llm_backend"] = backend
        data["enriched_total"] = sum(1 for it in items if it.get("llm_enriched"))
        data["items"] = items
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    save_partial()

    enriched_count = 0
    for i, it in enumerate(need_list[:MAX_PER_RUN]):
        print(f"  [{i+1}/{min(len(need_list), MAX_PER_RUN)}] [{it.get('lang','?')}] {it['title'][:60]}", flush=True)
        enrich_item(it)
        enriched_count += 1
        time.sleep(0.3)
        if enriched_count % 10 == 0:
            save_partial()

    save_partial()
    print(f"[done] enriched +{enriched_count} (total {data['enriched_total']}/{len(items)})", flush=True)


if __name__ == "__main__":
    main()
