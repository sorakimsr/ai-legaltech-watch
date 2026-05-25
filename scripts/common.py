"""
공통 유틸리티 — 텍스트 정제, 날짜 파싱, 카테고리 분류, 점수 산정
"""

import html
import re
from datetime import datetime, timezone

from dateutil import parser as dateparser


CATEGORY_KEYWORDS = {
    "legaltech": [
        "harvey", "legora", "mike oss", "hebbia", "ironclad", "spellbook",
        "robin ai", "lexis", "thomson reuters", "legal ai", "legal tech",
        "리걸테크", "리걸 ai", "법률 ai", "bhsn", "로앤컴퍼니", "로앤굿",
        "law firm", "lawyer", "litigation", "contract ai", "clm",
        "변호사", "로펌", "계약 검토", "엘박스", "인텔리콘", "lboxai",
        "lab ai", "evenup", "deepjudge",
    ],
    "papers": [
        "arxiv", "paper", "preprint", "neurips", "icml", "iclr", "acl",
        "논문", "발표", "연구", "research"
    ],
    "product": [
        "launch", "release", "announce", "introduce", "unveil", "rolls out",
        "출시", "공개", "선보", "발표", "ga", "general availability"
    ],
    "funding": [
        "raises", "raised", "funding", "valuation", "series ", "investment",
        "투자", "조달", "유치", "시리즈", "ipo", "acquires", "acquisition",
        "인수", "m&a"
    ],
    "adoption": [
        "adopts", "deploys", "rolls out", "implementing", "integrating",
        "case study", "도입", "활용 사례", "적용", "사례"
    ],
    "domestic": ["한국", "국내", "korea", "korean", "korean firm"],
    "policy": [
        "regulation", "regulator", "law", "act", "compliance", "government",
        "policy", "ban", "ruling", "court", "ftc", "doj", "eu ai act",
        "규제", "정책", "법안", "법령", "당국", "정부", "위원회",
        "trump", "white house"
    ],
    "ai-industry": [
        "openai", "anthropic", "claude", "gpt", "chatgpt", "gemini",
        "deepmind", "meta ai", "llama", "mistral", "xai", "grok",
        "nvidia", "microsoft ai", "perplexity"
    ],
}


HIGH_VALUE_KEYWORDS = {
    "harvey": 15, "legora": 15, "mike oss": 15, "mike legal": 12,
    "openai": 10, "anthropic": 10, "gpt-5": 12, "claude opus": 10, "claude sonnet": 8,
    "raises": 8, "funding": 8, "valuation": 8, "billion": 10, "series ": 6,
    "launches": 6, "announces": 5, "introduces": 5, "unveils": 6,
    "breakthrough": 10, "state-of-the-art": 8, "sota": 8,
    "리걸테크": 10, "법률 ai": 8, "리걸 ai": 10,
    "한국": 4, "korea": 4,
    "agent": 5, "agentic": 6, "multi-agent": 7,
}


def clean_text(text: str) -> str:
    """HTML 태그 제거 + 공백 정규화"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, max_len: int = 280) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def parse_date_safe(date_str: str):
    """다양한 형식의 날짜를 datetime으로 변환. 실패 시 None."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def categorize(title: str, summary: str, default_cats: list) -> list:
    """제목·요약 기반 카테고리 추론"""
    text = (title + " " + summary).lower()
    cats = list(default_cats)

    for cat, keywords in CATEGORY_KEYWORDS.items():
        if cat in cats:
            continue
        for kw in keywords:
            if kw in text:
                cats.append(cat)
                break

    return cats


def score_item(title: str, summary: str, date, categories: list) -> int:
    """간단한 중요도 점수 (0~100)"""
    score = 50
    text = (title + " " + summary).lower()

    for kw, pts in HIGH_VALUE_KEYWORDS.items():
        if kw in text:
            score += pts

    if "legaltech" in categories:
        score += 8
    if "papers" in categories:
        score += 5
    if "funding" in categories:
        score += 4
    if "domestic" in categories:
        score += 3

    if date:
        now = datetime.now(timezone.utc)
        if isinstance(date, str):
            date = parse_date_safe(date)
        if date and date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if date:
            delta_h = (now - date).total_seconds() / 3600
            if delta_h < 24:
                score += 10
            elif delta_h < 72:
                score += 5
            elif delta_h < 168:
                score += 2

    return max(0, min(100, score))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    # 트래킹 파라미터 제거
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
