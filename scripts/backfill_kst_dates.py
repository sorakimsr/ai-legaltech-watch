"""
v6.9: 기존 한국 매체(lang='ko') article의 date를 UTC 가정에서 KST 가정으로 보정.

배경:
  v6.9 이전엔 parse_date_safe가 timezone-naive datetime을 무조건 UTC로 가정.
  한국 매체 RSS pubDate (예: 'AI타임스 2026-05-26 18:58:52')는 KST인데 UTC로 저장됨.
  → 9시간 어긋남 → frontend KST 변환 시 5/27로 표시 (실제 5/26 발행)

backfill 로직:
  - lang='ko' article 선택
  - date가 '+00:00' (UTC) timezone offset이면 → KST로 simple replace ('+09:00')
    (실제 시각은 동일, 표시만 정확해짐)
  - date_unknown=True 또는 이미 +09:00이면 skip

사용:
  python scripts/backfill_kst_dates.py data/news.json
"""

import json
import sys
import re


def backfill(items):
    """items를 in-place로 수정. 보정된 항목 수 반환."""
    fixed = 0
    skipped = 0
    for it in items:
        if it.get('lang') != 'ko':
            continue
        if it.get('date_unknown'):
            continue
        date_str = it.get('date', '')
        if not date_str:
            continue
        # +00:00 또는 Z (UTC) → +09:00 (KST)
        # 단순 replace — 실제 시각 9시간 이동 효과
        if date_str.endswith('+00:00'):
            new_date = date_str[:-6] + '+09:00'
            it['date'] = new_date
            fixed += 1
        elif date_str.endswith('Z'):
            new_date = date_str[:-1] + '+09:00'
            it['date'] = new_date
            fixed += 1
        else:
            skipped += 1
    return fixed, skipped


def main():
    if len(sys.argv) < 2:
        print("usage: python backfill_kst_dates.py data/news.json [data/raw_news.json ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        print(f"\n=== {path} ===")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"  (file not found, skip)")
            continue

        items = data.get('items', [])
        if not items:
            print(f"  no items")
            continue

        fixed, skipped = backfill(items)
        print(f"  total: {len(items)}, ko-lang fixed: {fixed}, ko-lang skipped: {skipped}")

        # 백업 후 저장
        backup_path = path + '.bak'
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)  # backup은 compact
        except Exception:
            pass

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ saved (backup: {backup_path})")


if __name__ == '__main__':
    main()
