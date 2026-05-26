"""
2단계 — 유사 뉴스 자동 병합

raw_news.json을 읽어서 비슷한 뉴스(같은 사건을 다룬 여러 소스의 기사)를 그룹화합니다.
각 그룹에서 점수가 가장 높은 항목을 '대표(primary)'로 삼고,
나머지는 'related' 리스트에 담습니다.

알고리즘 (LLM 없이 빠르게):
1. 제목을 정규화하고 토큰화
2. 영문은 SequenceMatcher 비율 + 토큰 Jaccard 결합
3. 한국어/혼합은 토큰 Jaccard 위주
4. 임계값(0.55) 이상이면 같은 그룹

결과는 data/deduped_news.json 으로 저장.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "raw_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "deduped_news.json")
KST = timezone(timedelta(hours=9))

# 유사도 임계값 (v2.7 — 낮춤: 0.55 → 0.42, 대신 brand/proper-noun 보너스로 보강)
SIMILARITY_THRESHOLD = 0.42

# 영문 stopwords
STOPWORDS = set("""
a an the and or but of for to with in on at by from as is are was were
be been being have has had do does did will would shall should can could
may might must this that these those it its they them their there here
launches launched launching announce announces announced introduces introduced
unveils unveiled reveals revealed release released
""".split())

# 한국어 조사·자주 등장하는 일반어 (Jaccard 의미 약화 요인 제거)
KO_PARTICLES = ("로", "은", "는", "이", "가", "의", "을", "를", "에", "에서", "도", "와", "과", "랑")

# 양쪽 제목·요약에 동시 등장 시 동일 사건 확률 매우 높은 고유명사·키워드
PROPER_NOUN_BOOST_KEYS = [
    # AI 회사
    "openai", "anthropic", "claude", "chatgpt", "gemini",
    "perplexity", "mistral", "meta", "microsoft", "nvidia",
    # 리걸테크
    "harvey", "legora", "ironclad", "spellbook", "robin ai",
    "mike legal", "mike oss", "everlaw", "casetext",
    # 한국
    "bhsn", "로앤컴퍼니", "로앤굿", "케이스노트",
    # 정책 키워드 — 같은 정책 사건 다룰 가능성
    "ai 기본법", "ai act", "ai 가이드라인", "ai 규제",
    "나홀로 소송", "소송장",
]


def strip_korean_particle(token: str) -> str:
    """한국어 토큰 끝의 흔한 조사 제거 → 매칭률 향상"""
    for p in KO_PARTICLES:
        if len(token) > len(p) + 1 and token.endswith(p):
            return token[:-len(p)]
    return token


def tokenize(text: str):
    """제목을 토큰화 + 한국어 조사 정리"""
    text = text.lower()
    # 한국어/영문/숫자만 남기고 분리
    text = re.sub(r"[^\w가-힣]+", " ", text)
    raw = [t for t in text.split() if len(t) > 1 and t not in STOPWORDS]
    normalized = set()
    for t in raw:
        if re.search(r"[가-힣]", t):
            normalized.add(strip_korean_particle(t))
        else:
            normalized.add(t)
    return normalized


def proper_noun_overlap(a: str, b: str) -> int:
    """양쪽 제목에 같은 고유명사·키워드가 몇 개 동시 등장하는지"""
    a_l = a.lower()
    b_l = b.lower()
    return sum(1 for kw in PROPER_NOUN_BOOST_KEYS if kw in a_l and kw in b_l)


def first_meaningful_token(title: str) -> str:
    """제목의 첫 의미 토큰(회사명·기관명) 추출.
    v3.9: '에이블런, AI 챔피언…' 같은 한국 PR 기사가 같은 회사면 그룹되도록.
    """
    if not title:
        return ""
    # 쉼표·콜론·괄호 이전 부분 추출
    parts = re.split(r"[,:\[\]\(\)·]", title, maxsplit=1)
    head = parts[0].strip()
    # 너무 짧으면 (3자 미만) 사용 안 함 — '日', 'AI' 같은 약어 제외
    if len(head) < 3:
        return ""
    return head.lower()


def title_similarity(a: str, b: str) -> float:
    """두 제목의 유사도 (0~1).

    v2.7: 양쪽에 같은 고유명사(회사·정책 키워드)가 있으면 +0.2씩 보너스.
    v3.9: 양쪽 제목 첫 토큰(회사명)이 같으면 강력 보너스 (+0.3).
    Legora aOS 출시 같이 매체별 표현이 달라도 같은 사건으로 묶이도록.
    """
    if not a or not b:
        return 0.0

    a_tokens = tokenize(a)
    b_tokens = tokenize(b)
    if not a_tokens or not b_tokens:
        return 0.0

    jaccard = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))

    # 영문이면 SequenceMatcher 보강
    is_english_a = all(ord(c) < 128 for c in a)
    is_english_b = all(ord(c) < 128 for c in b)
    if is_english_a and is_english_b:
        seq_ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
        base = max(jaccard, seq_ratio * 0.6 + jaccard * 0.4)
    else:
        base = jaccard

    # 고유명사·키워드 보너스
    pn_overlap = proper_noun_overlap(a, b)
    if pn_overlap >= 1:
        base = min(1.0, base + 0.20 * pn_overlap)

    # v3.9: 첫 토큰(회사명) 동일 시 강력 보너스
    head_a = first_meaningful_token(a)
    head_b = first_meaningful_token(b)
    if head_a and head_b and head_a == head_b:
        base = min(1.0, base + 0.30)

    return base


def group_items(items):
    """유사한 항목들을 그룹화"""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    # 각 항목을 비교 (v2.7: 14일 → 30일로 확장, fetch retention과 일치)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(n):
        try:
            d_i = datetime.fromisoformat(items[i]["date"].replace("Z", "+00:00"))
            if d_i.tzinfo is None:
                d_i = d_i.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if d_i < cutoff:
            continue
        for j in range(i + 1, n):
            try:
                d_j = datetime.fromisoformat(items[j]["date"].replace("Z", "+00:00"))
                if d_j.tzinfo is None:
                    d_j = d_j.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            # 7일 이상 떨어져 있으면 같은 사건일 가능성 낮음
            if abs((d_i - d_j).total_seconds()) > 7 * 86400:
                continue

            sim = title_similarity(items[i]["title"], items[j]["title"])

            # v2.7: 같은 매체 + 같은 날짜에 핵심 명사가 충분히 겹치면 강한 신호
            same_source = items[i].get("source") == items[j].get("source")
            same_day = items[i].get("date", "")[:10] == items[j].get("date", "")[:10]
            if same_source and same_day:
                a_toks = tokenize(items[i]["title"])
                b_toks = tokenize(items[j]["title"])
                shared = a_toks & b_toks
                # 너무 일반적인 토큰(ai, 정부, 한국 등)은 제외하고 의미있는 명사만 카운트
                GENERIC = {"ai", "ml", "한국", "정부", "기업", "발표", "기술", "서비스", "시장"}
                meaningful = [t for t in shared if t not in GENERIC]
                # 의미 토큰 3개 이상 공유 OR 의미 토큰 2개 + 일반 토큰 2개 이상이면 강한 신호
                if len(meaningful) >= 3 or (len(meaningful) >= 2 and len(shared) >= 4):
                    sim = max(sim, SIMILARITY_THRESHOLD + 0.05)

            if sim >= SIMILARITY_THRESHOLD:
                union(i, j)

    # 그룹 모으기
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    return list(groups.values())


def main():
    print(f"[start] dedupe_similar @ {datetime.now(KST).isoformat()}", flush=True)
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    items = raw["items"]
    print(f"  input: {len(items)} items", flush=True)

    groups = group_items(items)
    print(f"  -> {len(groups)} groups (after merging)", flush=True)

    merged = []
    for grp in groups:
        # 점수가 가장 높은 항목을 대표로
        grp.sort(key=lambda i: items[i].get("score", 0), reverse=True)
        primary_idx = grp[0]
        primary = dict(items[primary_idx])

        related = [
            {
                "title": items[i]["title"],
                "url": items[i]["url"],
                "source": items[i]["source"],
                "date": items[i]["date"],
            }
            for i in grp[1:]
        ]
        primary["related_count"] = len(related)
        primary["related"] = related

        # 모든 출처의 카테고리 union
        all_cats = set(primary.get("categories", []))
        for i in grp[1:]:
            all_cats.update(items[i].get("categories", []))
        primary["categories"] = sorted(all_cats)

        merged.append(primary)

    # 점수+날짜순 정렬
    merged.sort(key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)

    payload = {
        "deduped_at": datetime.now(KST).isoformat(),
        "input_count": len(items),
        "output_count": len(merged),
        "sources": raw.get("sources", []),
        "items": merged,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
