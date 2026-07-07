"""
strategy_quality — 시사점 카드 품질 계층 (v6.17.0, 2026-07-07)

배경 (사용자 지적, 2026-07-07):
  7/7 daily에서 같은 기사 1건(LG 멀티에이전트 주가예측)이 TREND 01과 TREND 06
  두 카드의 유일한 근거로 재사용됨. 원인은 3중:
    ① 60:40 균형 룰이 한 기사를 법조·기술 두 버킷에서 재활용하도록 유도
    ② "sources 3~5개 필수" 룰이 프롬프트에만 있고 코드 검증 없음
    ③ 주제 선정과 카드 작성이 단일 24K 토큰 호출에 뒤엉켜 있음
  이 영역은 프롬프트 패치가 이미 다수 누적(v6.15.20/.21/.26/.51)된 곳이라
  구조 개선으로 대응 (feedback: 미봉책 반복 시 구조 재설계).

이 모듈이 제공하는 3계층:
  1. cluster_topics()      — Stage A: 기사 → 주제 클러스터 (배타적 근거 배분)
  2. write_cluster_cards() — Stage B: 클러스터별 소형 LLM 호출로 카드 작성
                             (24K 단일 호출의 truncation 실패 모드를 구조적으로 제거)
  3. validate_cards()      — deterministic 검증 게이트 (LLM 비용 0):
                             근거 URL 겹침·주제 유사도 기반 중복 카드 drop.
                             full/incremental/weekly/monthly 모든 경로에 적용.

부가: load_bookmark_hints() — 사용자가 사이트에서 ⭐ 저장한 기사(ground truth)를
  주제 선정 가중치 힌트로 Stage A 프롬프트에 주입.

설계 원칙:
  - 실패 시 항상 기존(레거시 단일 호출) 경로로 폴백 — 카드 0건 사고 방지
  - validate_cards는 비어있지 않은 입력에서 절대 0건을 반환하지 않음 (safeguard)
  - 환경변수 STRATEGY_TWO_STAGE=0 으로 2단계 경로 비활성화 가능
"""

import glob
import json
import os
import re
import sys
from urllib.parse import urlparse

from llm_client import call_llm_json


# ============================================================================
# 1. 북마크 ground-truth 힌트
# ============================================================================

def _slug_to_text(url: str) -> str:
    """URL slug에서 사람이 읽을 수 있는 주제 텍스트 추출.
    예: .../ex-latham-associate-unveils-free-legal-ai-tool → 'ex latham associate unveils free legal ai tool'
    매칭 실패 시 도메인명 반환."""
    try:
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if segments:
            slug = segments[-1]
            slug = re.sub(r"\.(html?|php|aspx?)$", "", slug)
            words = [w for w in re.split(r"[-_+]", slug) if w and not w.isdigit()]
            if len(words) >= 3:
                return " ".join(words)
        return parsed.netloc or ""
    except Exception:
        return ""


def load_bookmark_hints(root_dir: str, max_hints: int = 15) -> list:
    """사용자 북마크(⭐ 저장 기사)를 주제 선정 힌트 문자열 목록으로 변환.

    소스: data/bookmarks_export_*.json (수동 export) + data/_local_bookmarks.json (gitignore).
    제목 해석: 현재 news.json에 URL이 남아 있으면 실제 제목, 없으면 URL slug.
    파일 없으면 빈 목록 (Stage A는 힌트 없이도 동작)."""
    paths = sorted(glob.glob(os.path.join(root_dir, "data", "bookmarks_export_*.json")))
    local = os.path.join(root_dir, "data", "_local_bookmarks.json")
    if os.path.exists(local):
        paths.append(local)

    saved = {}  # url -> savedAt
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("items", {})
            if isinstance(items, dict):
                for u, meta in items.items():
                    ts = meta.get("savedAt", 0) if isinstance(meta, dict) else 0
                    saved[u] = max(saved.get(u, 0), ts or 0)
        except Exception:
            continue
    if not saved:
        return []

    title_by_url = {}
    news_path = os.path.join(root_dir, "data", "news.json")
    if os.path.exists(news_path):
        try:
            with open(news_path, "r", encoding="utf-8") as f:
                news = json.load(f)
            for it in news.get("items", []):
                u = it.get("url")
                if u in saved and it.get("title"):
                    title_by_url[u] = it["title"]
        except Exception:
            pass

    hints = []
    for u, _ts in sorted(saved.items(), key=lambda kv: -kv[1]):
        t = (title_by_url.get(u) or _slug_to_text(u)).strip()
        if t and len(t) > 8 and t not in hints:
            hints.append(t[:90])
        if len(hints) >= max_hints:
            break
    return hints


# ============================================================================
# 2. Stage A — 주제 클러스터링
# ============================================================================

CLUSTER_PROMPT = """당신은 한국 대형로펌 경영전략팀 브리핑의 **편집장**입니다. 아래 {n}개 기사를 '{period_label} 전략 시사점 카드'의 주제 클러스터로 묶는 편집 회의를 진행합니다. 카드 작성은 다음 단계이므로, 여기서는 **주제 선정과 근거 배분만** 결정합니다.

[기사 목록 — 각 항목 앞 번호가 인덱스]
{news_blob}
{hints_block}
[응답 형식 — JSON 객체만, 다른 텍스트 절대 금지]
{{
  "clusters": [
    {{"topic": "[카드 주제 한 줄, 20~40자]", "bucket": "legal 또는 frontier", "indexes": [번호, ...], "reason": "[이 주제가 카드 가치가 있는 이유 한 문장]"}}
  ]
}}

규칙 (모두 필수):
1. **각 기사 인덱스는 최대 1개 클러스터에만 속한다 — 재사용 절대 금지.** 한 기사가 법조·기술 양면을 가지면(예: 대기업의 금융 AI 도입 = 기술 사례이자 규제 이슈) **더 결정적인 관점 하나를 골라 그 클러스터에만** 배정하고, topic에 두 관점을 모두 담아라. 같은 사건을 두 클러스터로 쪼개는 것은 최악의 편집이다.
2. 클러스터 수: {period_label} 기준 5~10개. 클러스터당 indexes 1~6개.
3. **indexes가 1개뿐인 클러스터는 다음 경우에만 허용**: (a) 6대 핵심 어젠다(판결문 공개·데이터 인프라 / AI 규제·개인정보 / 로펌·법무팀 AI 도입 / 법조계 AI 정책 / AI 책임·소송·판례 / 글로벌 AI 거버넌스)의 정책·입법·판결 시그널, 또는 (b) 플래그십 모델 release·시장 구조를 바꾸는 단독 사건. 그 외 단일 기사는 클러스터화하지 말 것 (기사 재서술은 카드가 아니다).
4. bucket 균형: legal(법조·거버넌스 교차) 다수 ~60%, frontier(AI 기술·산업·논문) ~40% — 단, **균형을 채우기 위해 같은 사건을 재활용하거나 가치 없는 기사를 억지로 묶지 말 것**. 데이터가 부족하면 그 bucket은 적어도 된다.
5. 카드 가치가 없는 기사(단순 홍보·중복 보도·주변부)는 어느 클러스터에도 넣지 않는다.
6. 유사 주제 기사 여러 건은 반드시 하나의 클러스터로 (예: 로펌 3곳의 AI 도입 보도 3건 → 1클러스터).
"""

HINTS_BLOCK_TEMPLATE = """
[독자(경영전략팀 대표)가 과거 직접 ⭐ 저장한 콘텐츠 — 실제 가치 판단의 ground truth. 주제 선정 시 이런 계열에 가중치를 둘 것]
{hints}
"""


def cluster_topics(sorted_items: list, period_label: str, bookmark_hints: list = None) -> list:
    """Stage A: 기사 목록 → 주제 클러스터 목록.

    Returns: [{"topic": str, "bucket": str, "indexes": [int(1-based)], "reason": str}]
             실패(빈 응답·형식 오류) 시 [] — 호출자는 레거시 경로로 폴백.
    Deterministic 후처리: 범위 밖 인덱스 제거, 중복 배정 제거(선착순), 빈 클러스터 제거, 최대 12개.
    """
    if not sorted_items:
        return []

    news_lines = []
    for i, it in enumerate(sorted_items, 1):
        summary = it.get("summary_ko") or it.get("summary", "")[:200]
        news_lines.append(
            f"{i}. [{it.get('source', '?')}, {it.get('date', '')[:10]}] "
            f"{it.get('title', '')[:120]}\n   요약: {summary[:200]}"
        )
    news_blob = "\n".join(news_lines)

    hints_block = ""
    if bookmark_hints:
        hints_block = HINTS_BLOCK_TEMPLATE.format(
            hints="\n".join(f"  · {h}" for h in bookmark_hints[:15])
        )

    prompt = CLUSTER_PROMPT.format(
        n=len(sorted_items),
        period_label=period_label,
        news_blob=news_blob,
        hints_block=hints_block,
    )

    result = call_llm_json(prompt, max_tokens=3000, temperature=0.2)
    clusters_raw = result.get("clusters") if isinstance(result, dict) else None
    if not isinstance(clusters_raw, list):
        print("  [stage-A] 클러스터 응답 형식 오류 → 폴백", file=sys.stderr)
        return []

    seen_idx = set()
    clusters = []
    for c in clusters_raw[:12]:
        if not isinstance(c, dict) or not c.get("topic"):
            continue
        idxs = []
        for v in (c.get("indexes") or []):
            try:
                i = int(v)
            except (ValueError, TypeError):
                continue
            if 1 <= i <= len(sorted_items) and i not in seen_idx:
                seen_idx.add(i)
                idxs.append(i)
        if not idxs:
            continue
        bucket = str(c.get("bucket", "")).strip().lower()
        clusters.append({
            "topic": str(c["topic"]).strip()[:60],
            "bucket": bucket if bucket in ("legal", "frontier") else "legal",
            "indexes": idxs,
            "reason": str(c.get("reason", "")).strip()[:200],
        })

    n_articles = sum(len(c["indexes"]) for c in clusters)
    print(f"  [stage-A] {len(clusters)} 클러스터 / 기사 {n_articles}건 배정 "
          f"(legal {sum(1 for c in clusters if c['bucket'] == 'legal')} : "
          f"frontier {sum(1 for c in clusters if c['bucket'] == 'frontier')})", flush=True)
    return clusters


# ============================================================================
# 3. Stage B — 클러스터별 카드 작성 (소형 호출)
# ============================================================================

CARD_PROMPT = """당신은 **한국 대형로펌 경영전략팀의 시니어 컨설턴트**입니다. 독자는 전략·기획과 AI 업무를 동시에 수행하는 실무자입니다.

편집 회의에서 아래 주제가 {period_label} 시사점 카드로 확정되었습니다. 배정된 근거 기사만으로 카드 1개를 작성하세요.

[확정 주제] {topic}
[주제 성격] {bucket_desc}
[근거 기사 — 번호는 전체 목록 기준 인덱스이므로 그대로 인용할 것]
{news_blob}

[응답 형식 — JSON 객체만, 다른 텍스트 절대 금지]
{{
  "title": "[20~35자 헤드라인]",
  "body": "[4~5문장, 250~450자]",
  "action": "[2~3문장, 150~280자]",
  "sources": [{indexes}]
}}

규칙:
- body: (1) 어떤 흐름인가(구체 회사명·제품명·금액·날짜) (2) 왜 한국 실무자에게 의미 있나 (3) 표면 아래 시장 구조·역학 (4) 향후 어디로 가나. 일반론·교과서적 표현 금지. **첫 문장에 근거 인덱스를 명시** (예: "오늘(3, 7번) 보도에 따르면...").
- {bucket_rule}
- action: 동사형·서술형 2~3문장 ("~한다", "~해보자"). 명사형 종결 금지. (1) 첫 단계 동작 (2) 다음 검증·산출물 (3) 성공·실패 판단 지표 — 최소 둘 포함.
- **시점/기한 표현 절대 금지** ("지금 당장", "즉시", "이번 주", "이번 달", "빠른 시일 내", "우선", "곧" 등).
- **굵게 강조(`**...**`)는 카드 전체(body+action)에 3~6개 필수** — 인과·판단·시사 구절에만 (예: "**책임 경계가 명확히 설계된 아키텍처를 선택**"). 회사명·금액·기법명·논문제목은 절대 강조하지 말 것.
- sources에는 위 근거 기사 인덱스만. 본문과 무관한 인덱스 금지.
"""

BUCKET_DESC = {
    "legal": "법조·거버넌스 교차 이슈 — 한국 법무·로펌·법조계 함의가 핵심",
    "frontier": "프런티어 AI·기술 동향 — 그 발전 자체의 의미(역량 도약·방법론·시장 구조·경쟁 구도)가 핵심",
}

BUCKET_RULE = {
    "legal": "한국 대형로펌 경영전략팀 관점에서 법무 수요·리스크·자문 기회를 구체적으로.",
    "frontier": "**법무 수요/리스크로 환원하지 말 것.** 발전 자체의 의미를 충실히 쓰고, 법조 함의가 있으면 마지막 한 문장으로만 덧붙인다 (없으면 생략).",
}


def write_cluster_cards(clusters: list, sorted_items: list, period_label: str) -> list:
    """Stage B: 클러스터별 소형 LLM 호출로 카드 생성.

    Returns: generate_cards의 cards_raw와 동일 형식
             [{"tag","title","body","action","sources"}].
    개별 클러스터 실패는 skip — 다른 클러스터에 영향 없음 (구조적 격리).
    전체 실패(0건) 시 [] — 호출자가 레거시 폴백.
    """
    cards_raw = []
    for ci, cluster in enumerate(clusters, 1):
        idxs = cluster["indexes"]
        news_lines = []
        for i in idxs:
            it = sorted_items[i - 1]
            summary = it.get("summary_ko") or it.get("summary", "")[:250]
            news_lines.append(
                f"{i}. [{it.get('source', '?')}, {it.get('date', '')[:10]}] "
                f"{it.get('title', '')[:140]}\n   요약: {summary[:250]}"
            )
        bucket = cluster.get("bucket", "legal")
        prompt = CARD_PROMPT.format(
            period_label=period_label,
            topic=cluster["topic"],
            bucket_desc=BUCKET_DESC.get(bucket, BUCKET_DESC["legal"]),
            bucket_rule=BUCKET_RULE.get(bucket, BUCKET_RULE["legal"]),
            news_blob="\n".join(news_lines),
            indexes=", ".join(str(i) for i in idxs),
        )
        result = call_llm_json(prompt, max_tokens=2200, temperature=0.35)
        if not isinstance(result, dict) or not all(k in result for k in ("title", "body", "action")):
            print(f"  [stage-B] 클러스터 {ci} '{cluster['topic'][:30]}' 카드 실패 → skip", file=sys.stderr)
            continue

        # sources: LLM 반환값을 클러스터 배정 인덱스로 제한 (배타 배분 보존)
        raw_sources = result.get("sources") or []
        sources = []
        if isinstance(raw_sources, list):
            for v in raw_sources:
                try:
                    i = int(v)
                except (ValueError, TypeError):
                    continue
                if i in idxs and i not in sources:
                    sources.append(i)
        if not sources:
            sources = list(idxs)

        cards_raw.append({
            "tag": f"TREND {ci:02d} · {cluster['topic']}",
            "title": str(result["title"]).strip(),
            "body": str(result["body"]).strip(),
            "action": str(result["action"]).strip(),
            "sources": sources,
        })

    print(f"  [stage-B] {len(cards_raw)}/{len(clusters)} 카드 생성", flush=True)
    return cards_raw


# ============================================================================
# 4. Deterministic 검증 게이트 (LLM 비용 0)
# ============================================================================

_TOKEN_RE = re.compile(r"[A-Za-z가-힣0-9]{2,}")

_TITLE_STOPWORDS = {
    "trend", "카드", "오늘", "이번", "주간", "월간", "동향", "확산", "가속",
    "국내", "글로벌", "한국", "시장", "산업", "구조", "전략", "관련",
}


def _card_urls(card: dict) -> set:
    return {c.get("url") for c in card.get("citations", []) if c.get("url")}


def _title_tokens(card: dict) -> set:
    text = f"{card.get('tag', '')} {card.get('title', '')}".lower()
    return {t for t in _TOKEN_RE.findall(text) if t not in _TITLE_STOPWORDS}


def validate_cards(cards: list, existing_cards: list = None, priority_fn=None):
    """생성된 카드 목록의 deterministic 품질 검증.

    Drop 규칙:
      ① 근거 URL 겹침 — 앞선 카드(또는 기존 카드)와 Jaccard ≥ 0.5, 또는
         어느 한쪽 URL 집합이 다른 쪽의 부분집합 → 같은 사건의 재서술로 판정, drop.
         (7/7 LG 사례: TREND 01과 06의 URL 집합 동일 → 06 drop되었을 것)
      ② 주제 유사 — tag+title 토큰 Jaccard ≥ 0.6 → drop.
    유지 우선순위: 배열 앞 카드 우선 (호출 전 중요도 정렬 전제) + existing_cards 우선.
    _emergency 카드는 검증 면제. full 경로에서는 입력이 비어있지 않으면 0건 반환 안 함.
    priority_fn: 예약 파라미터 — 향후 tier 기반 drop 규칙(단일 근거 등) 도입 시 사용.

    Returns: (kept_cards, dropped_list)  — dropped_list: [(card, reason)]
    """
    if not cards:
        return [], []

    kept, dropped = [], []
    context = list(existing_cards or [])

    for card in cards:
        if card.get("_emergency"):
            kept.append(card)
            context.append(card)
            continue

        urls = _card_urls(card)
        tokens = _title_tokens(card)
        drop_reason = None

        for prev in context:
            purls = _card_urls(prev)
            if urls and purls:
                inter = len(urls & purls)
                union = len(urls | purls)
                if inter and (inter / union >= 0.5 or urls <= purls or purls <= urls):
                    drop_reason = (f"근거 중복 (기존 '{str(prev.get('title', ''))[:40]}'와 "
                                   f"URL {inter}/{union} 겹침)")
                    break
            ptokens = _title_tokens(prev)
            if tokens and ptokens:
                t_inter = len(tokens & ptokens)
                t_union = len(tokens | ptokens)
                if t_union and t_inter / t_union >= 0.6:
                    drop_reason = f"주제 유사 (기존 '{str(prev.get('title', ''))[:40]}')"
                    break

        if drop_reason:
            dropped.append((card, drop_reason))
        else:
            kept.append(card)
            context.append(card)

    # safeguard: full 생성 경로에서 전부 drop되는 병리적 상황 방지.
    # 단, 증분 경로(existing_cards 있음)에서는 전부 중복이면 0건이 올바른 결과.
    if cards and not kept and not existing_cards:
        kept = [cards[0]]
        dropped = [(c, r) for c, r in dropped if c is not cards[0]]

    if dropped:
        for c, r in dropped:
            print(f"  [검증 게이트 drop] '{str(c.get('title', ''))[:50]}' — {r}", flush=True)
    # 단일 근거 카드는 drop하지 않되 모니터링 로그 (frontier 단독 논문 카드 등 정당한 케이스 존재)
    singles = [c for c in kept if len(_card_urls(c)) <= 1 and not c.get("_emergency")]
    if singles:
        print(f"  [검증 게이트] 단일 근거 카드 {len(singles)}건 유지 (모니터링)", flush=True)

    return kept, dropped
