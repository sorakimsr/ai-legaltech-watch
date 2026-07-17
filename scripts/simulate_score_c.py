"""Phase B 시뮬레이션 — 기존 news.json에 대해 A vs C 점수 재계산·분포 비교.

실행: python3 scripts/simulate_score_c.py
(docs/SCORE_REDESIGN_C.md의 마이그레이션 Phase B에 해당 — 빌드 없이 오프라인 검증)
"""
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import score_item_a, score_item_c, parse_date_safe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "data", "news.json"), encoding="utf-8") as f:
        items = json.load(f)["items"]
    print(f"items: {len(items)}")

    rows = []
    for it in items:
        title = it.get("title") or ""
        summary = it.get("summary_ko") or it.get("summary") or ""
        cats = it.get("categories") or []
        ps = it.get("persona_score")
        src = it.get("source") or ""
        dt = parse_date_safe(it.get("date")) if it.get("date") else None
        a = score_item_a(title, summary, dt, cats, persona_score=ps, source=src)
        c = score_item_c(title, summary, dt, cats, persona_score=ps, source=src)
        rows.append((a, c, ps, title))

    for label, idx in (("A", 0), ("C", 1)):
        vals = [r[idx] for r in rows]
        alive = [v for v in vals if v >= 35]
        print(f"\n[{label}] median={statistics.median(vals)}  "
              f"drop(<35)={sum(1 for v in vals if v < 35)} ({sum(1 for v in vals if v < 35)/len(vals):.0%})  "
              f"70+={sum(1 for v in vals if v >= 70)} ({sum(1 for v in vals if v >= 70)/len(vals):.0%})  "
              f"90+={sum(1 for v in vals if v >= 90)} ({sum(1 for v in vals if v >= 90)/len(vals):.0%})")
        hist = Counter((v // 10) * 10 for v in vals)
        for b in sorted(hist):
            bar = "#" * max(1, hist[b] * 60 // len(vals))
            print(f"    {b:>3}~ {hist[b]:>6} {bar}")

    # persona별 C 점수 평균 (단조 증가해야 정상)
    by_ps = {}
    for a, c, ps, _t in rows:
        by_ps.setdefault(ps, []).append(c)
    print("\npersona_score → C 평균 (단조 증가 확인):")
    for ps in sorted([k for k in by_ps if k is not None]) + [None]:
        v = by_ps.get(ps)
        if v:
            print(f"  ps={ps}: n={len(v):>5}  mean={statistics.mean(v):.1f}")

    # 큰 폭 하락/상승 예시
    movers = sorted(rows, key=lambda r: r[1] - r[0])
    print("\nC에서 가장 크게 하락한 5건 (인플레이션 제거 대상):")
    for a, c, ps, t in movers[:5]:
        print(f"  A={a:>3} → C={c:>3} (ps={ps}) {t[:60]}")
    print("\nC에서 가장 크게 상승한 5건:")
    for a, c, ps, t in movers[-5:]:
        print(f"  A={a:>3} → C={c:>3} (ps={ps}) {t[:60]}")


if __name__ == "__main__":
    main()
