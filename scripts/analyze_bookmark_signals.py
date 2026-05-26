"""
북마크 회귀 분석 — 사용자 ground-truth 시그널 분석 도구 (v6.0, 검토 외 메모).

사용자(daibfy.com)가 localStorage에 저장한 북마크 데이터를 입력으로 받아,
현재 score 시스템과 어긋나는지(저장한 항목의 평균/분포가 cut-off 35에 근접한지) 분석합니다.

사용법:
  1. daibfy.com → DevTools → Application → Local Storage → daibfy.com
     `daibfy_saved_v1` 값을 복사해 `data/_local_bookmarks.json` 으로 저장 (gitignore됨)
  2. python scripts/analyze_bookmark_signals.py [경로]
  3. 결과: 저장한 항목의 score·카테고리·4축 시그널 분포 출력 → 점수 정책 조정 근거

연관 메모: spaces/.../memory/daibfy_content_value_signal.md
"""

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from common import score_item, categorize, detect_score_buckets  # noqa: E402

DEFAULT_BOOKMARKS = os.path.join(ROOT, "data", "_local_bookmarks.json")
NEWS_JSON = os.path.join(ROOT, "data", "news.json")


def load_bookmarks(path: str):
    if not os.path.exists(path):
        print(f"[error] 북마크 파일이 없습니다: {path}")
        print("  사용법은 모듈 docstring 참고.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # localStorage 포맷: {items: {url: {savedAt}}, strategy: {key: {...}}}
    items = raw.get("items", {})
    return items  # {url: {savedAt}}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BOOKMARKS
    saved = load_bookmarks(path)
    print(f"[loaded] {len(saved)} bookmarked URLs")

    # news.json에서 매칭
    with open(NEWS_JSON, "r", encoding="utf-8") as f:
        news = json.load(f)
    by_url = {it["url"]: it for it in news.get("items", [])}

    matched, unmatched = [], []
    for url in saved:
        if url in by_url:
            matched.append(by_url[url])
        else:
            unmatched.append(url)

    print(f"  matched in news.json: {len(matched)}")
    print(f"  unmatched (30일 이전): {len(unmatched)}")
    if not matched:
        print("[done] 매칭 결과 없음 — 분석 종료.")
        return

    # === 점수 분포 ===
    scores = [it.get("score", 0) for it in matched]
    scores_sorted = sorted(scores)
    print(f"\n== 점수 분포 (n={len(scores)}) ==")
    print(f"  min/p25/median/p75/max: "
          f"{scores_sorted[0]} / "
          f"{scores_sorted[len(scores)//4]} / "
          f"{scores_sorted[len(scores)//2]} / "
          f"{scores_sorted[3*len(scores)//4]} / "
          f"{scores_sorted[-1]}")
    avg = sum(scores) / len(scores)
    print(f"  mean: {avg:.1f}")
    under_cut = sum(1 for s in scores if s < 35)
    print(f"  score < 35 (cut-off): {under_cut} ({100*under_cut/len(scores):.0f}%)  "
          f"⚠️ ground truth가 cut-off 아래면 점수 정책 재조정 필요")

    # === 카테고리 분포 ===
    cat_counter = Counter()
    for it in matched:
        for c in it.get("categories", []):
            cat_counter[c] += 1
    print(f"\n== 카테고리 분포 ==")
    for c, n in cat_counter.most_common():
        print(f"  {c:15s} {n}")

    # === 4축 시그널 강도 ===
    print(f"\n== 4축 시그널 평균 강도 ==")
    bucket_sums = defaultdict(float)
    for it in matched:
        buckets = detect_score_buckets(it.get("title", ""), it.get("summary", ""))
        for k, v in buckets.items():
            bucket_sums[k] += v
    for k in ("law", "global", "policy", "promo"):
        print(f"  {k:8s} {bucket_sums[k] / len(matched):.3f}")

    # === 권장 액션 ===
    print(f"\n== 권장 액션 ==")
    if under_cut / len(scores) > 0.2:
        print("  - cut-off 35가 너무 높을 가능성 — 평균/분포 보고 30~33으로 낮추기 검토.")
    top_cats = [c for c, _ in cat_counter.most_common(3)]
    print(f"  - 사용자가 자주 저장하는 카테고리: {top_cats} → 보너스 가중치 점검.")
    print("  - bookmark + score 일치도가 낮은 항목은 dump_examples.py로 케이스 검토 권장.")


if __name__ == "__main__":
    main()
