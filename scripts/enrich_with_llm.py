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

# v2.8.5: 최근 N일 이내 항목은 캐시 무시하고 강제 재 enrich
# (프롬프트 변경 후 새 음영 정책 적용용)
REFRESH_RECENT_DAYS = int(os.environ.get("ENRICH_REFRESH_DAYS", "0"))


# v2.8: 의미론적 강조로 전환 — 고유명사가 아니라 의사결정·영향력 구절에만 **굵게**
_HIGHLIGHT_RULES = """- **굵게(`**...**`)는 "의미론적으로 의사결정에 직결되는 구절"에만 적용** (사용자 정책):

  강조해야 할 것 (✅ 인과·필요·판단·시사 구절):
    예시) "단일 LLM 선택은 이미 낡은 질문이고, 에이전트 간 신뢰·조정 계층이 새 병목",
    "RAG 파이프라인을 구축하고 방치하는 운영 방식은 재검토가 필요한 시점",
    "성공한 목표당 비용으로 KPI를 재설계해야",
    "온프레미스 또는 폐쇄망 요구가 도입 속도를 제한하는 현실적 제약",
    "책임 경계가 명확히 설계된 아키텍처를 선택",
    "협상 레버리지가 옮겨갔다", "벤더 종속이 풀린다",
    "한국 기업 환경에서는 개인정보보호법상 국외 데이터 이전 제한이 도입의 현실적 장벽"
  → "X는 Y다", "A가 B의 병목", "C 요구가 D를 제한" 같은 인과·판단 구절만.

  강조 금지 (❌ 단순 고유명사·금액·기법명·기관명):
    "OpenAI", "Anthropic", "Sequoia Capital", "수출입은행", "KB금융",
    "Harvey", "Foundation Protocol", "40억 달러", "RAG"
  → 회사명·금액·기법명은 그대로 적되 절대 굵게 X. 강조는 그 사실의 "해석·의미·행동 지침"에만."""

PROMPT_EN_FULL = """다음 영문 뉴스를 한국 전략·기획·AI 업무 담당자 관점에서 분석해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

규칙:
""" + _HIGHLIGHT_RULES + """
- '시사점:' 같은 접두어 없이 본문만.
- 시점 표현(지금 당장 / 이번 주 안에 / 이번 달 내 / 즉시 등) 사용 금지.

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "summary_ko": "2~3문장. 핵심 사실 중심. 80~150자. 단정 어조 지양.",
  "insight_ko": "1~2문장. 본인 업무에 적용할 액션 가능한 시사점. 60~120자."
}}
"""

PROMPT_KO_INSIGHT_ONLY = """다음 한국어 뉴스에 대한 전략·기획·AI 업무 시사점만 작성해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

규칙:
""" + _HIGHLIGHT_RULES + """
- 시점 표현(지금 당장 / 이번 주 안에 / 이번 달 내 / 즉시 등) 사용 금지.

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
        # v2.7.1: 모든 영문 카드 — summary_ko + insight_ko 둘 다 (threshold 무관)
        prompt = PROMPT_EN_FULL.format(
            title=title, source=source, date=date,
            summary=summary, categories=categories,
        )
        result = call_llm_json(prompt, max_tokens=500, temperature=0.3)
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
    """이 항목이 enrich 대상인지 판단

    v2.7.1: 모든 영문 카드는 summary_ko + insight_ko 둘 다 있어야 함.
    하나라도 빠지면 재 enrich.
    """
    lang = item.get("lang", "en")
    score = item.get("score", 0)

    if lang == "en":
        # 영문은 summary_ko + insight_ko 둘 다 필요
        if not item.get("summary_ko") or not item.get("insight_ko"):
            return True
        return False
    elif lang == "ko":
        # 한국어는 insight가 있을 가치 있는 경우만
        if score >= INSIGHT_THRESHOLD_KO and not item.get("insight_ko"):
            return True
        return False
    return False


def main():
    backend = detect_backend()
    model_env = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL") or "(default)"
    print(f"[start] enrich_with_llm @ {datetime.now(KST).isoformat()}", flush=True)
    print(f"  [llm] backend: {backend} · model: {model_env}", flush=True)

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

    # v2.8.5: 최근 N일 항목은 캐시 무시 (force refresh)
    refresh_cutoff = None
    if REFRESH_RECENT_DAYS > 0:
        from datetime import datetime as _dt
        cutoff_dt = _dt.now(KST) - timedelta(days=REFRESH_RECENT_DAYS)
        refresh_cutoff = cutoff_dt.strftime("%Y-%m-%d")
        print(f"  [refresh] 최근 {REFRESH_RECENT_DAYS}일치 (>= {refresh_cutoff}) 캐시 무시하고 재 enrich", flush=True)

    def is_recent(it):
        if not refresh_cutoff:
            return False
        d = (it.get("date", "") or "")[:10]
        if not d:
            return False
        return d >= refresh_cutoff

    cached_count = 0
    refresh_count = 0
    for it in items:
        # 최근 N일 항목 → 캐시 무시하고 enrich 대상으로 → 기존 summary_ko/insight_ko 삭제
        if is_recent(it):
            if it.get("summary_ko") or it.get("insight_ko"):
                refresh_count += 1
            it.pop("summary_ko", None)
            it.pop("insight_ko", None)
            it.pop("llm_enriched", None)
            continue
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
    if REFRESH_RECENT_DAYS > 0:
        print(f"  cached: {cached_count}, refreshed (cleared): {refresh_count}, need enrich: {len(need_list)} (max per run: {MAX_PER_RUN})", flush=True)
    else:
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
