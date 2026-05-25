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

# 유사도 임계값
SIMILARITY_THRESHOLD = 0.55

# 영문 stopwords
STOPWORDS = set("""
a an the and or but of for to with in on at by from as is are was were
be been being have has had do does did will would shall should can could
may might must this that these those it its they them their there here
""".split())


def tokenize(text: str):
    """제목을 토큰화"""
    text = text.lower()
    # 한국어/영문/숫자만 남기고 분리
    text = re.sub(r"[^\w가-힣]+", " ", text)
    tokens = [t for t in text.split() if len(t) > 1 and t not in STOPWORDS]
    return set(tokens)


def title_similarity(a: str, b: str) -> float:
    """두 제목의 유사도 (0~1)"""
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
        return max(jaccard, seq_ratio * 0.7 + jaccard * 0.3)

    return jaccard


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

    # 각 항목을 비교 (시간 절약을 위해 최근 14일 내만 매칭)
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
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
