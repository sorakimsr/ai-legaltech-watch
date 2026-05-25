"""
5단계 — 마크다운 export → Obsidian vault repo

data/news.json 을 읽어서 vault repo 디렉토리에 마크다운 파일을 생성합니다.

구조:
  vault/
    news/YYYY/MM/YYYY-MM-DD-slug.md      ← 일반 뉴스 (한국어 요약·시사점·백링크)
    papers/arxiv-NNNN.NNNNN.md            ← arXiv 논문 (abstract + 발췌 + PDF 링크)
    entities/{Name}.md                    ← 엔티티 MOC (자동 백링크 집계)
    digests/YYYY-MM-DD.md                 ← 일일 다이제스트 (TOP 항목 + 전략 카드)
    _index.md                             ← 전체 인덱스

환경변수:
- VAULT_DIR (필수): 클론된 vault repo의 로컬 경로
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_PATH = os.path.join(ROOT_DIR, "data", "news.json")
VAULT_DIR = os.environ.get("VAULT_DIR", os.path.join(ROOT_DIR, "_vault_local"))

KST = timezone(timedelta(hours=9))


# ===== 유틸 =====

def slugify(text: str, max_len: int = 60) -> str:
    """제목을 파일명 안전한 slug로"""
    text = text.lower()
    text = re.sub(r"[^\w가-힣\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text[:max_len].strip("-")


def yaml_safe(value):
    """YAML frontmatter 안전 직렬화"""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [yaml_safe(v) for v in value]
        return "[" + ", ".join(items) + "]"
    # 문자열
    s = str(value).replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def write_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {yaml_safe(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def is_arxiv(item: dict) -> bool:
    return item.get("source_type") == "arxiv" or "arxiv.org" in item.get("url", "")


def extract_arxiv_id(url: str):
    """arXiv URL에서 ID 추출 (e.g., 2503.11074)"""
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url)
    if m:
        return m.group(1)
    return None


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


# ===== 노트 작성 =====

def write_news_note(item: dict, vault_dir: str) -> str:
    """일반 뉴스 마크다운 노트 작성. 경로 반환."""
    date_str = item.get("date", "")[:10] or datetime.now(KST).strftime("%Y-%m-%d")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        dt = datetime.now(KST)
    yyyy, mm = dt.strftime("%Y"), dt.strftime("%m")

    slug = slugify(item.get("title", "untitled"))[:50]
    filename = f"{date_str}-{slug}.md"
    rel_dir = os.path.join("news", yyyy, mm)
    full_dir = os.path.join(vault_dir, rel_dir)
    ensure_dir(full_dir)
    full_path = os.path.join(full_dir, filename)

    # frontmatter
    fm = {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source": item.get("source", ""),
        "source_type": item.get("source_type", ""),
        "lang": item.get("lang", ""),
        "date": date_str,
        "first_seen": item.get("first_seen", "")[:19],
        "score": item.get("score", 0),
        "categories": item.get("categories", []),
        "entities": item.get("entities", []),
        "related_count": item.get("related_count", 0),
        "llm_enriched": item.get("llm_enriched", False),
        "type": "news",
    }

    # body
    parts = [write_frontmatter(fm), ""]
    parts.append(f"# {item.get('title', '')}\n")
    parts.append(f"> **출처**: [{item.get('source', '')}]({item.get('url', '')})  ")
    parts.append(f"> **발행**: {date_str} · **중요도**: {item.get('score', 0)}\n")

    if item.get("summary_ko"):
        parts.append("## 한국어 요약\n")
        parts.append(item["summary_ko"] + "\n")

    if item.get("summary"):
        parts.append("## 원문 요약 (Original)\n")
        parts.append(item["summary"] + "\n")

    if item.get("insight_ko"):
        parts.append("## 시사점 (전략·기획·AI 업무 관점)\n")
        parts.append(item["insight_ko"] + "\n")

    # 엔티티 백링크
    entities = item.get("entities") or []
    if entities:
        parts.append("## 관련 엔티티\n")
        parts.append(" · ".join(f"[[{e}]]" for e in entities) + "\n")

    # 유사 뉴스
    related = item.get("related") or []
    if related:
        parts.append("## 유사 보도\n")
        for r in related:
            parts.append(f"- [{r.get('source','?')}] [{r.get('title','')[:100]}]({r.get('url','')})")
        parts.append("")

    parts.append("\n---\n")
    parts.append(f"[원문 보기]({item.get('url', '')})")

    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return full_path


def write_paper_note(item: dict, vault_dir: str) -> str:
    """arXiv 논문 노트 작성"""
    arxiv_id = extract_arxiv_id(item.get("url", "")) or "unknown"
    slug = slugify(item.get("title", "paper"))[:40]
    filename = f"arxiv-{arxiv_id}-{slug}.md"
    rel_dir = "papers"
    full_dir = os.path.join(vault_dir, rel_dir)
    ensure_dir(full_dir)
    full_path = os.path.join(full_dir, filename)

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id != "unknown" else ""
    abs_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id != "unknown" else item.get("url", "")

    fm = {
        "title": item.get("title", ""),
        "arxiv_id": arxiv_id,
        "url": abs_url,
        "pdf_url": pdf_url,
        "source": item.get("source", "arXiv"),
        "lang": item.get("lang", "en"),
        "date": item.get("date", "")[:10],
        "score": item.get("score", 0),
        "categories": item.get("categories", []),
        "entities": item.get("entities", []),
        "type": "paper",
    }

    parts = [write_frontmatter(fm), ""]
    parts.append(f"# {item.get('title', '')}\n")
    parts.append(f"> **arXiv**: [{arxiv_id}]({abs_url}) · **PDF**: [download]({pdf_url})\n")

    if item.get("summary_ko"):
        parts.append("## 한국어 요약\n")
        parts.append(item["summary_ko"] + "\n")

    if item.get("summary"):
        parts.append("## Abstract\n")
        parts.append(item["summary"] + "\n")

    if item.get("insight_ko"):
        parts.append("## 시사점\n")
        parts.append(item["insight_ko"] + "\n")

    entities = item.get("entities") or []
    if entities:
        parts.append("## 관련 엔티티\n")
        parts.append(" · ".join(f"[[{e}]]" for e in entities) + "\n")

    parts.append("\n## 발췌 (TODO)\n")
    parts.append("_PDF 본문에서 핵심 발췌를 자동 추출하는 단계는 Phase 2에서 추가_\n")
    parts.append("\n---\n")
    parts.append(f"[Abstract]({abs_url}) · [PDF]({pdf_url})")

    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return full_path


def write_entity_moc(entity: str, items: list, vault_dir: str) -> str:
    """엔티티별 MOC (Map of Content) 노트 작성.
    items: 이 엔티티가 등장하는 모든 항목 리스트."""
    rel_dir = "entities"
    full_dir = os.path.join(vault_dir, rel_dir)
    ensure_dir(full_dir)
    filename = f"{slugify(entity, 80)}.md"
    full_path = os.path.join(full_dir, filename)

    items_sorted = sorted(items, key=lambda x: x.get("date", ""), reverse=True)

    fm = {
        "title": entity,
        "type": "entity",
        "item_count": len(items_sorted),
    }

    parts = [write_frontmatter(fm), ""]
    parts.append(f"# {entity}\n")
    parts.append(f"> **관련 항목**: {len(items_sorted)}건\n")
    parts.append("## 최근 보도·논문\n")
    for it in items_sorted[:30]:
        date = (it.get("date", "") or "")[:10]
        title = it.get("title", "")
        url = it.get("url", "")
        source = it.get("source", "")
        parts.append(f"- **{date}** [{source}] [{title}]({url})")
    if len(items_sorted) > 30:
        parts.append(f"\n_... 외 {len(items_sorted) - 30}건_")

    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return full_path


def write_daily_digest(items: list, strategy: list, vault_dir: str) -> str:
    """일일 다이제스트 노트 (TOP 항목 + 오늘의 전략 카드)"""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    rel_dir = "digests"
    full_dir = os.path.join(vault_dir, rel_dir)
    ensure_dir(full_dir)
    filename = f"{today}.md"
    full_path = os.path.join(full_dir, filename)

    # 점수 상위 10개
    top10 = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:10]

    parts = [write_frontmatter({"title": f"{today} 데일리 브리핑", "type": "digest", "date": today}), ""]
    parts.append(f"# {today} (KST) AI & Legaltech 데일리 브리핑\n")

    parts.append("## 🎯 오늘의 전략·기획 시사점\n")
    for c in strategy:
        parts.append(f"### {c.get('tag', '')}\n")
        parts.append(f"**{c.get('title','')}**\n")
        parts.append(c.get("body", "") + "\n")
        parts.append(f"> **액션**: {c.get('action','')}\n")
        cites = c.get("citations") or []
        if cites:
            parts.append("\n근거:")
            for ref in cites:
                parts.append(f"- [{ref.get('source','')}] [{ref.get('title','')}]({ref.get('url','')})")
        parts.append("")

    parts.append("\n## 📰 중요도 TOP 10\n")
    for i, it in enumerate(top10, 1):
        date = (it.get("date","") or "")[:10]
        parts.append(f"{i}. **[중요도 {it.get('score',0)}]** [{it.get('source','')}] [{it.get('title','')}]({it.get('url','')}) · {date}")
        if it.get("insight_ko"):
            parts.append(f"   - 💡 {it['insight_ko']}")

    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return full_path


def write_index(stats: dict, vault_dir: str):
    """vault 루트 _index.md"""
    full_path = os.path.join(vault_dir, "_index.md")
    today = datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)")
    lines = [
        "# AI & Legaltech Watch — Knowledge Vault",
        "",
        f"_Auto-generated · 마지막 갱신: {today}_",
        "",
        "## 통계",
        f"- 뉴스: **{stats['news']}** 건",
        f"- 논문: **{stats['papers']}** 건",
        f"- 엔티티: **{stats['entities']}** 개",
        f"- 다이제스트: **{stats['digests']}** 일",
        "",
        "## 폴더",
        "- `news/` — 일반 뉴스 (YYYY/MM 트리)",
        "- `papers/` — arXiv 논문",
        "- `entities/` — 엔티티 MOC (회사·인물·제품·컨셉)",
        "- `digests/` — 일일 다이제스트",
    ]
    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ===== 메인 =====

def main():
    print(f"[start] export_to_vault @ {datetime.now(KST).isoformat()}", flush=True)
    print(f"  vault dir: {VAULT_DIR}", flush=True)

    if not os.path.exists(VAULT_DIR):
        os.makedirs(VAULT_DIR, exist_ok=True)

    with open(NEWS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    strategy = data.get("strategy", [])

    # 엔티티별 매핑
    entity_map = defaultdict(list)

    news_cnt = 0
    paper_cnt = 0
    for it in items:
        if is_arxiv(it):
            write_paper_note(it, VAULT_DIR)
            paper_cnt += 1
        else:
            write_news_note(it, VAULT_DIR)
            news_cnt += 1
        for ent in (it.get("entities") or []):
            entity_map[ent].append(it)

    # 엔티티 MOC
    for ent, ent_items in entity_map.items():
        write_entity_moc(ent, ent_items, VAULT_DIR)
    entity_cnt = len(entity_map)

    # 다이제스트 (오늘)
    write_daily_digest(items, strategy, VAULT_DIR)

    # 인덱스
    digests_dir = os.path.join(VAULT_DIR, "digests")
    digest_cnt = len([f for f in os.listdir(digests_dir) if f.endswith(".md")]) if os.path.exists(digests_dir) else 1
    write_index({
        "news": news_cnt,
        "papers": paper_cnt,
        "entities": entity_cnt,
        "digests": digest_cnt,
    }, VAULT_DIR)

    print(f"[done] news={news_cnt}, papers={paper_cnt}, entities={entity_cnt}, digests={digest_cnt}", flush=True)


if __name__ == "__main__":
    main()
