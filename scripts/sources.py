"""
AI & Legaltech Watch — 소스 카탈로그

데이터 소스를 한 곳에서 관리합니다.

각 소스: (name, url, source_type, default_categories, lang)
- source_type: rss / arxiv / korean / blog / google_news / semantic_scholar
  ★ papers 카테고리는 arxiv·semantic_scholar 타입에만 부여
"""

from urllib.parse import quote_plus


def _gnews(query: str, lang: str = "ko", country: str = "KR") -> str:
    """Google News RSS URL 생성 — 사람이 읽을 수 있는 query 그대로 두고 자동 encode."""
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"


SOURCES = [
    # ====================================================================
    # 글로벌 AI 산업 (영문)
    # ====================================================================
    ("OpenAI Blog", "https://openai.com/blog/rss.xml", "rss", ["ai-industry", "product"], "en"),
    # v2.7: Anthropic·Meta·Mistral·Stability·Perplexity 공식 RSS feed가 403/404 또는 비표준 XML 응답 →
    # Google News site: 쿼리로 우회 (회사 자체 발행 글이 Google에 인덱싱되면 잡힘)
    ("Anthropic News", "https://news.google.com/rss/search?q=site%3Aanthropic.com%2Fnews&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry", "product"], "en"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/", "rss", ["ai-industry", "product"], "en"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml", "rss", ["ai-industry"], "en"),
    ("Google Research", "https://research.google/blog/rss/", "rss", ["ai-industry"], "en"),
    ("Meta AI Blog", "https://news.google.com/rss/search?q=site%3Aai.meta.com%2Fblog&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry", "product"], "en"),
    ("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/", "rss", ["ai-industry", "product"], "en"),
    ("NVIDIA Blog", "https://blogs.nvidia.com/feed/", "rss", ["ai-industry"], "en"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "rss", ["ai-industry"], "en"),
    ("Mistral AI Blog", "https://news.google.com/rss/search?q=site%3Amistral.ai+(news+OR+launches+OR+announces+OR+release)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry", "product"], "en"),
    ("Stability AI", "https://news.google.com/rss/search?q=%22Stability+AI%22+(news+OR+release+OR+announces+OR+launches)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry", "product"], "en"),
    ("Perplexity Blog", "https://news.google.com/rss/search?q=site%3Aperplexity.ai+OR+%22Perplexity%22+(launches+OR+announces+OR+blog)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry", "product"], "en"),

    # ====================================================================
    # AI 뉴스 매체 (영문)
    # ====================================================================
    ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "rss", ["ai-industry"], "en"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "rss", ["ai-industry"], "en"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "rss", ["ai-industry"], "en"),
    # v2.7: 실패 RSS는 Google News site: 쿼리로 일괄 우회
    ("The Verge AI", "https://news.google.com/rss/search?q=site%3Atheverge.com+(AI+OR+%22artificial+intelligence%22)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss", "rss", ["ai-industry"], "en"),
    ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab", "rss", ["ai-industry"], "en"),
    ("Axios AI", "https://api.axios.com/feed/", "rss", ["ai-industry"], "en"),
    ("The Information AI", "https://news.google.com/rss/search?q=site%3Atheinformation.com+AI&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Semianalysis", "https://www.semianalysis.com/feed", "rss", ["ai-industry"], "en"),
    ("The Decoder", "https://the-decoder.com/feed/", "rss", ["ai-industry"], "en"),
    ("Import AI (Jack Clark)", "https://news.google.com/rss/search?q=%22Import+AI%22+OR+(%22Jack+Clark%22+AI)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Ben's Bites", "https://news.google.com/rss/search?q=%22Ben%27s+Bites%22+OR+site%3Abensbites.com&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("The Batch (DeepLearning.AI)", "https://news.google.com/rss/search?q=%22The+Batch%22+%22DeepLearning.AI%22+OR+site%3Adeeplearning.ai&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("AI Snake Oil", "https://www.aisnakeoil.com/feed", "blog", ["ai-industry", "policy"], "en"),
    ("Marginal Revolution AI", "https://news.google.com/rss/search?q=site%3Amarginalrevolution.com+AI&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Last Week in AI", "https://lastweekin.ai/feed", "blog", ["ai-industry"], "en"),

    # ====================================================================
    # 리걸테크 (영문)
    # ====================================================================
    ("Artificial Lawyer", "https://www.artificiallawyer.com/feed/", "rss", ["legaltech"], "en"),
    ("Legal IT Insider", "https://legaltechnology.com/feed/", "rss", ["legaltech"], "en"),
    ("Legal Cheek", "https://www.legalcheek.com/feed/", "rss", ["legaltech"], "en"),
    ("LawSites (Bob Ambrogi)", "https://www.lawnext.com/feed", "rss", ["legaltech"], "en"),
    ("ABA Journal Tech", "https://news.google.com/rss/search?q=site%3Aabajournal.com+(%22legal+technology%22+OR+%22legal+tech%22+OR+AI)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Above the Law", "https://abovethelaw.com/feed/", "rss", ["legaltech"], "en"),
    ("Law.com Legal Tech", "https://news.google.com/rss/search?q=site%3Alaw.com+(%22legaltech%22+OR+%22legal+tech%22+OR+%22legal+AI%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Legal Futures", "https://www.legalfutures.co.uk/feed", "rss", ["legaltech"], "en"),
    ("Global Legal Post", "https://news.google.com/rss/search?q=site%3Agloballegalpost.com&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Stanford CodeX", "https://news.google.com/rss/search?q=site%3Alaw.stanford.edu+(%22CodeX%22+OR+%22legal+informatics%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    # v2.7: Harvey·Legora 공식 블로그 RSS 미제공 → Google News site:로 우회
    ("Harvey Blog", "https://news.google.com/rss/search?q=site%3Aharvey.ai+OR+%22Harvey+AI%22+(blog+OR+announces+OR+launches+OR+raises)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech", "product"], "en"),
    ("Legora Blog", "https://news.google.com/rss/search?q=site%3Alegora.com+OR+%22Legora%22+(legal+OR+blog+OR+announces+OR+launches)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech", "product"], "en"),

    # ====================================================================
    # v4.6: AI 회사 공식 발표 (Anthropic·OpenAI 공식 채널)
    # ====================================================================
    ("Anthropic News", "https://news.google.com/rss/search?q=site%3Aanthropic.com+(news+OR+announces+OR+launches+OR+claude)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("OpenAI News (Latest)", "https://news.google.com/rss/search?q=site%3Aopenai.com+(blog+OR+news+OR+launches+OR+announces)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Apple AI", "https://news.google.com/rss/search?q=site%3Aapple.com+(%22Apple+Intelligence%22+OR+%22Apple+AI%22)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", "rss", ["ai-industry"], "en"),
    ("Cohere Blog", "https://news.google.com/rss/search?q=site%3Acohere.com+(blog+OR+announces+OR+launches)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),

    # ====================================================================
    # v4.6: 분석·인사이트 뉴스레터 (Substack)
    # ====================================================================
    ("Stratechery", "https://stratechery.com/feed/", "rss", ["ai-industry"], "en"),
    ("Latent Space (Swyx)", "https://www.latent.space/feed", "rss", ["ai-industry"], "en"),
    ("Pragmatic Engineer", "https://newsletter.pragmaticengineer.com/feed", "rss", ["ai-industry"], "en"),
    ("The Rundown AI", "https://news.google.com/rss/search?q=%22The+Rundown+AI%22+OR+site%3Atherundown.ai&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Big Technology", "https://news.google.com/rss/search?q=%22Big+Technology%22+(Newsletter+OR+Substack)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),

    # ====================================================================
    # v4.6: 글로벌 법률 매체 (Bloomberg Law·Reuters Legal·JD Supra)
    # ====================================================================
    ("Bloomberg Law AI", "https://news.google.com/rss/search?q=site%3Anews.bloomberglaw.com+(AI+OR+%22artificial+intelligence%22+OR+%22legal+tech%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Reuters Legal Tech", "https://news.google.com/rss/search?q=site%3Areuters.com+(%22legal+tech%22+OR+%22law+firm+AI%22+OR+%22legal+AI%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("JD Supra AI Legal", "https://news.google.com/rss/search?q=site%3Ajdsupra.com+(AI+OR+%22artificial+intelligence%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("American Lawyer Tech", "https://news.google.com/rss/search?q=site%3Aamericanlawyer.com+(tech+OR+AI+OR+innovation)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Legal IT Today", "https://news.google.com/rss/search?q=site%3Alegalittoday.com&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),

    # ====================================================================
    # v4.6: PR Wire (회사 보도자료 1차 source)
    # ====================================================================
    ("PRNewswire AI", "https://news.google.com/rss/search?q=site%3Aprnewswire.com+(%22artificial+intelligence%22+OR+%22AI+platform%22+OR+%22AI+launches%22)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Business Wire AI", "https://news.google.com/rss/search?q=site%3Abusinesswire.com+(%22artificial+intelligence%22+OR+%22AI+platform%22+OR+%22AI+raises%22)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("PRNewswire Legal Tech", "https://news.google.com/rss/search?q=site%3Aprnewswire.com+(%22legal+tech%22+OR+%22law+firm+AI%22+OR+%22legaltech%22)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),

    # ====================================================================
    # AI 논문 (arXiv API) — papers 카테고리는 여기에서만 부여
    # v2.7: 기존 /rss/ 는 announce-date만 줘서 실제 발행/수정일을 못 잡음 →
    # /api/query 로 교체 (각 entry에 published[v1 제출일] + updated[최신 revision] 정확히 제공)
    # v6.15.24 (2026-05-28): 6개 카테고리 query 통합 → 1번 호출.
    #   기존: 6개 entry × 8초 sleep ≈ 50초 + 429 만나면 90초 backoff 누적.
    #   변경: 단일 OR query (max_results=200) → arXiv 429 사실상 차단.
    #   cs.CY의 default ["papers","policy"] 손실은 categorize가 본문 키워드로 자동 보완.
    #   각 entry의 arxiv_primary_category(cs.AI/cs.LG 등)는 그대로 유지됨 (UI/분류 영향 X).
    ("arXiv AI/CL/LG/IR/MA/CY",
     "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG+OR+cat:cs.IR+OR+cat:cs.MA+OR+cat:cs.CY&max_results=200&sortBy=lastUpdatedDate&sortOrder=descending",
     "arxiv", ["papers"], "en"),
    # Papers With Code RSS 미제공 → Semantic Scholar가 동등 커버. 보조로 Google News 우회.
    ("Papers With Code", "https://news.google.com/rss/search?q=site%3Apaperswithcode.com+OR+%22paperswithcode%22+AI&hl=en&gl=US&ceid=US:en", "google_news", ["papers"], "en"),

    # ====================================================================
    # 국내 매체 (한국어)
    # ====================================================================
    ("AI타임스", "https://www.aitimes.com/rss/allArticle.xml", "korean", ["ai-industry", "domestic"], "ko"),
    # AI타임스 정책 카테고리 RSS 실패 → Google News 우회
    ("AI타임스 (정책)", "https://news.google.com/rss/search?q=site%3Aaitimes.com+(%22%EC%A0%95%EC%B1%85%22+OR+%22%EA%B7%9C%EC%A0%9C%22)&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["policy", "domestic"], "ko"),
    # 법률신문 RSS 실패 → Google News 우회
    ("법률신문 (테크)", "https://news.google.com/rss/search?q=site%3Alawtimes.co.kr+(%EB%A6%AC%EA%B1%B8%ED%85%8C%ED%81%AC+OR+AI+OR+%EA%B8%B0%EC%88%A0)&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["legaltech", "domestic"], "ko"),
    ("법률신문 (전체)", "https://news.google.com/rss/search?q=site%3Alawtimes.co.kr&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["domestic"], "ko"),
    ("ZDNet Korea", "https://feeds.feedburner.com/zdkorea", "korean", ["ai-industry", "domestic"], "ko"),
    # 디지털타임스 IT 카테고리 RSS 실패 → Google News 우회
    ("디지털타임스 IT", "https://news.google.com/rss/search?q=site%3Adt.co.kr+(AI+OR+%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+OR+%EA%B8%B0%EC%88%A0)&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("전자신문 AI", "https://rss.etnews.com/Section902.xml", "korean", ["ai-industry", "domestic"], "ko"),
    ("바이라인네트워크", "https://byline.network/feed/", "korean", ["ai-industry", "domestic"], "ko"),
    # v2.7: 디일렉(반도체·디스플레이 중심), 플래텀(일반 스타트업) — AI 관련성 약함, 제거
    # 스타트업 투자 동향은 Naver "AI 스타트업 투자" 쿼리에서 충분히 잡힘
    ("벤처스퀘어", "https://www.venturesquare.net/feed", "korean", ["domestic", "funding"], "ko"),
    # 더밀크 RSS 실패 → Google News 우회
    ("더밀크", "https://news.google.com/rss/search?q=site%3Athemiilk.com+OR+%22%EB%8D%94%EB%B0%80%ED%81%AC%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("매일경제 IT", "https://www.mk.co.kr/rss/30000023/", "korean", ["domestic"], "ko"),
    ("한국경제 IT", "https://www.hankyung.com/feed/it", "korean", ["domestic"], "ko"),

    # ====================================================================
    # Google News RSS — 키워드 기반 (v2.7: 특수문자(·, &, -, vs) 제거 + 개별 회사명 분리)
    # 패턴: https://news.google.com/rss/search?q={url-encoded-keyword}&hl={lang}&gl={country}&ceid={country}:{lang}
    # 원칙:
    #   - 회사명·고유명사는 큰따옴표("...")로 묶어 정확 매칭
    #   - 한 쿼리당 OR 키워드 4개 이내 (Google이 길면 자름)
    #   - 특수문자(·, &, -)는 사용 금지. 공백 OR 사용
    # ====================================================================

    # === 영문 — AI 프론티어 회사 (개별) ===
    ("Google News: OpenAI (EN)", "https://news.google.com/rss/search?q=%22OpenAI%22+(launches+OR+announces+OR+releases+OR+raises)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Anthropic Claude (EN)", "https://news.google.com/rss/search?q=%22Anthropic%22+OR+%22Claude%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Google Gemini DeepMind (EN)", "https://news.google.com/rss/search?q=%22Google+Gemini%22+OR+%22DeepMind%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: xAI Grok (EN)", "https://news.google.com/rss/search?q=%22xAI%22+OR+%22Grok%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Mistral (EN)", "https://news.google.com/rss/search?q=%22Mistral+AI%22+OR+%22Mistral+Large%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Meta AI Llama (EN)", "https://news.google.com/rss/search?q=%22Meta+AI%22+OR+%22Llama%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Perplexity (EN)", "https://news.google.com/rss/search?q=%22Perplexity%22+AI&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: NVIDIA AI (EN)", "https://news.google.com/rss/search?q=%22NVIDIA%22+(AI+OR+GPU+OR+CUDA)&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: AI Frontier (EN)", "https://news.google.com/rss/search?q=%22frontier+AI%22+OR+%22frontier+model%22+OR+%22foundation+model%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),

    # === 영문 — 리걸테크 회사 (개별) ===
    ("Google News: Harvey (EN)", "https://news.google.com/rss/search?q=%22Harvey%22+(legal+OR+law+OR+AI)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Legora (EN)", "https://news.google.com/rss/search?q=%22Legora%22+legal&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Mike OSS (EN)", "https://news.google.com/rss/search?q=%22MikeOss%22+OR+%22Mike+OSS%22+OR+(%22Mike%22+legal+AI)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Hebbia (EN)", "https://news.google.com/rss/search?q=%22Hebbia%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Ironclad (EN)", "https://news.google.com/rss/search?q=%22Ironclad%22+(contract+OR+AI+OR+legal)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Spellbook (EN)", "https://news.google.com/rss/search?q=%22Spellbook%22+(legal+OR+contract+OR+AI)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Robin AI Casetext Everlaw (EN)", "https://news.google.com/rss/search?q=%22Robin+AI%22+OR+%22Casetext%22+OR+%22Everlaw%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Eltemate (EN)", "https://news.google.com/rss/search?q=%22Eltemate%22+OR+%22Hogan+Lovells%22+AI&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Law firm AI (EN)", "https://news.google.com/rss/search?q=%22law+firm%22+AI+(adoption+OR+implementation+OR+rollout)&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),

    # === 영문 — 분야·실무 use case ===
    ("Google News: AI Agents (EN)", "https://news.google.com/rss/search?q=%22AI+agent%22+OR+%22autonomous+agent%22+OR+%22multi+agent%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: AI Governance (EN)", "https://news.google.com/rss/search?q=%22AI+governance%22+OR+%22AI+ethics%22+OR+%22responsible+AI%22&hl=en&gl=US&ceid=US:en", "google_news", ["policy"], "en"),
    ("Google News: AI Regulation EU Act (EN)", "https://news.google.com/rss/search?q=%22AI+regulation%22+OR+%22EU+AI+Act%22+OR+%22AI+compliance%22&hl=en&gl=US&ceid=US:en", "google_news", ["policy"], "en"),
    ("Google News: AI Adoption Enterprise (EN)", "https://news.google.com/rss/search?q=%22AI+adoption%22+OR+%22enterprise+AI%22+OR+%22AI+transformation%22+OR+%22AX%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: AI Funding (EN)", "https://news.google.com/rss/search?q=%22AI+startup%22+(raises+OR+%22Series+B%22+OR+%22Series+C%22+OR+valuation)&hl=en&gl=US&ceid=US:en", "google_news", ["funding"], "en"),
    ("Google News: Contract Legal AI Use Cases (EN)", "https://news.google.com/rss/search?q=%22contract+AI%22+OR+%22contract+review%22+OR+%22due+diligence%22+OR+%22legal+research+AI%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Open source LLM (EN)", "https://news.google.com/rss/search?q=%22open+source+LLM%22+OR+%22Llama%22+OR+%22DeepSeek%22+OR+%22Qwen%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: In house AI Build (EN)", "https://news.google.com/rss/search?q=%22in+house+AI%22+OR+%22AI+ROI%22+OR+%22vendor+lock%22+OR+%22AI+cost%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),

    # v2.7 추가 — 영문 EN 분야 보강
    ("Google News: Generative AI (EN)", _gnews('"generative AI" OR "gen AI" OR "GenAI"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI Coding Tools (EN)", _gnews('"GitHub Copilot" OR "Cursor AI" OR "Cody" OR "Codex" OR "AI code"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI Search Browser (EN)", _gnews('"AI search" OR "ChatGPT search" OR "Perplexity" OR "AI browser"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI Safety Alignment (EN)", _gnews('"AI safety" OR "AI alignment" OR "responsible AI" OR "AI red team"', "en", "US"), "google_news", ["policy"], "en"),
    ("Google News: AI Chip Infra (EN)", _gnews('"AI chip" OR "AI infrastructure" OR "Cerebras" OR "Groq" OR "TPU"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Multimodal Voice AI (EN)", _gnews('"multimodal AI" OR "voice AI" OR "video generation AI" OR "Sora"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI M&A (EN)", _gnews('"AI acquisition" OR "AI merger" OR "AI startup acquired"', "en", "US"), "google_news", ["funding"], "en"),
    ("Google News: Legal AI Big Law (EN)", _gnews('"Big Law" AI OR "Magic Circle" AI OR "AmLaw" AI', "en", "US"), "google_news", ["legaltech"], "en"),

    # === 한국어(+영문 OR) — 리걸테크 핵심 ===
    # v2.7: 한국 매체의 영어 기사도 잡히도록 영문 키워드를 OR로 같이 포함
    ("Google News: 리걸테크 (KR)", _gnews('리걸테크 OR legaltech OR "legal tech"'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 법률 AI (KR)", _gnews('"법률 AI" OR "법무 AI" OR "법률 인공지능" OR "legal AI"'), "google_news", ["legaltech", "domestic"], "ko"),
    # v2.7: 회사·제품 단독 쿼리로 분리 (OR 묶음은 Google News 결과 가시성↓)
    ("Google News: BHSN (KR)", _gnews("BHSN"), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 로앤컴퍼니 (KR)", _gnews('"로앤컴퍼니" OR "LawCompany"'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 로앤굿 (KR)", _gnews('"로앤굿"'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 엘박스 (KR)", _gnews('"엘박스" OR "Lbox" OR "lbox.kr"'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 케이스노트 (KR)", _gnews('"케이스노트" OR "casenote"'), "google_news", ["legaltech", "domestic"], "ko"),

    # === 한국어(+영문 OR) — AI 회사·제품 (회사명 단독 쿼리) ===
    ("Google News: OpenAI (KR)", _gnews('"OpenAI" OR "오픈AI"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: ChatGPT (KR)", _gnews('"ChatGPT" OR "챗GPT"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Anthropic (KR)", _gnews('"Anthropic" OR "앤트로픽"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Claude (KR)", _gnews('"Claude" OR "클로드"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Gemini (KR)", _gnews('"Gemini" OR "제미나이"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Google DeepMind (KR)", _gnews('"Google AI" OR "DeepMind" OR "딥마인드"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: xAI (KR)", _gnews('"xAI"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Grok (KR)", _gnews('"Grok" OR "그록"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Meta AI (KR)", _gnews('"Meta AI" OR "메타 AI"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Llama (KR)", _gnews('"Llama" OR "라마"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Mistral (KR)", _gnews('"Mistral" OR "미스트랄"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Perplexity (KR)", _gnews('"Perplexity" OR "퍼플렉시티"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 생성형 AI 에이전트 (KR)", _gnews('"생성형 AI" OR "AI 에이전트" OR "generative AI" OR "AI agent"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: AI 도입 전환 AX (KR)", _gnews('"AI 도입" OR "AI 전환" OR AX OR "사내 AI" OR "AI adoption" OR "AI transformation"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 엔터프라이즈 AI (KR)", _gnews('"엔터프라이즈 AI" OR "기업용 AI" OR "enterprise AI"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 로펌 법무법인 AI (KR)", _gnews('"로펌 AI" OR "법무법인 AI" OR "변호사 AI" OR "law firm AI"'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 계약서 AI 자동화 (KR)", _gnews('"계약서 AI" OR "계약 자동화" OR "contract AI"'), "google_news", ["legaltech", "domestic"], "ko"),

    # === 한국어(+영문 OR) — 정책·규제·거버넌스 ===
    ("Google News: AI 규제 기본법 (KR)", _gnews('"AI 규제" OR "AI 기본법" OR "AI regulation" OR "AI Act"'), "google_news", ["policy", "domestic"], "ko"),
    ("Google News: AI 가이드라인 거버넌스 (KR)", _gnews('"AI 가이드라인" OR "AI 거버넌스" OR "AI 윤리" OR "AI governance" OR "AI ethics"'), "google_news", ["policy", "domestic"], "ko"),
    ("Google News: EU AI Act (KR)", _gnews('"EU AI Act" OR "EU AI 법"'), "google_news", ["policy", "domestic"], "ko"),

    # === v3.9: v3.8 영문 키워드 — Google News 영문 검색 ===
    ("Google News: AI Orchestration (EN)", _gnews('"AI orchestration" OR "agent orchestration" OR "AI orchestrator"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Multi-agent System (EN)", _gnews('"multi agent" OR "multiagent" OR "multi agent system" OR "agent infrastructure"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI Engineering Roles (EN)", _gnews('"prompt engineering" OR "context engineering" OR "harness engineering" OR "clone engineering"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Forward Deployed Engineer (EN)", _gnews('"forward deployed engineer" OR "FDE role"', "en", "US"), "google_news", ["adoption"], "en"),
    ("Google News: Open Source AI (EN)", _gnews('"open source AI" OR "open source LLM" OR "open weight" OR "open-weight model"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: AI Coding Tools (EN)", _gnews('"Claude Code" OR "Cursor AI" OR "Windsurf" OR "GitHub Copilot" OR "vibe coding"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Model Context Protocol (EN)", _gnews('"Model Context Protocol" OR "MCP server" OR "MCP client"', "en", "US"), "google_news", ["ai-industry"], "en"),

    # === v3.9: 거버넌스·감사 영문 ===
    ("Google News: AI Audit Red Teaming (EN)", _gnews('"AI audit" OR "AI red teaming" OR "AI safety evaluation"', "en", "US"), "google_news", ["governance"], "en"),
    ("Google News: Explainable AI (EN)", _gnews('"explainable AI" OR "XAI" OR "trustworthy AI" OR "model card"', "en", "US"), "google_news", ["governance"], "en"),

    # === v3.9: Sovereign AI 영문 ===
    ("Google News: Sovereign AI (EN)", _gnews('"sovereign AI" OR "AI sovereignty" OR "data sovereignty AI"', "en", "US"), "google_news", ["policy"], "en"),

    # === v3.9: 실무 도입 영문 ===
    ("Google News: AI Deployment ROI (EN)", _gnews('"AI deployment case" OR "AI ROI" OR "AI pilot" OR "AI POC"', "en", "US"), "google_news", ["adoption"], "en"),

    # === v3.12: 주요 frontier·open-source LLM 모델 (EN) ===
    ("Google News: Claude Mythos (EN)", _gnews('"Claude Mythos" OR "Anthropic Mythos"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Gemma Google (EN)", _gnews('"Gemma" Google AI OR "Gemma 3" OR "Gemma model"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: DeepSeek (EN)", _gnews('"DeepSeek" AI OR "DeepSeek V3" OR "DeepSeek R1"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Qwen Alibaba (EN)", _gnews('"Qwen" Alibaba OR "Qwen 2.5" OR "Qwen 3"', "en", "US"), "google_news", ["ai-industry"], "en"),

    # === v3.12: AI 모델 벤치마크·평가 (EN) ===
    ("Google News: LLM Benchmark (EN)", _gnews('"LLM benchmark" OR "AI benchmark" OR "model evaluation"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: MMLU GPQA HumanEval (EN)", _gnews('"MMLU" OR "GPQA" OR "HumanEval"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: SWE-bench ARC-AGI (EN)", _gnews('"SWE bench" OR "SWEbench" OR "ARC AGI" OR "ARCAGI" OR "LiveBench"', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Chatbot Arena LMSYS (EN)", _gnews('"Chatbot Arena" OR "LMSYS" OR "AI leaderboard"', "en", "US"), "google_news", ["ai-industry"], "en"),

    # ====================================================================
    # v6.13 (2026-05-27): 키워드 확장 — Microsoft/Copilot/Gemini Workspace 등 (사용자 요청)
    # ====================================================================
    # 한국어 — Microsoft/Copilot 전용 (지금까지 한국어 검색에서 누락)
    ("Google News: Microsoft Copilot (KR)", _gnews('"마이크로소프트" OR "Microsoft" OR "Copilot" OR "코파일럿" OR "MS 코파일럿"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: GitHub Copilot 코딩 (KR)", _gnews('"GitHub Copilot" OR "깃허브 코파일럿" OR "AI 코딩" OR "AI 코드"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Microsoft Azure AI (KR)", _gnews('"Azure AI" OR "Azure OpenAI" OR "MS Azure"'), "google_news", ["ai-industry", "domestic"], "ko"),
    # 한국어 — Gemini Workspace / Claude for Work / Perplexity Enterprise (보강)
    ("Google News: Gemini Workspace (KR)", _gnews('"Gemini for Workspace" OR "Gemini Enterprise" OR "Google Workspace AI"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Claude for Work (KR)", _gnews('"Claude for Enterprise" OR "Claude for Work" OR "Claude Team"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Perplexity Enterprise (KR)", _gnews('"Perplexity Enterprise" OR "퍼플렉시티 엔터프라이즈"'), "google_news", ["ai-industry", "domestic"], "ko"),
    # 한국어 — AI 에이전트 사이버 보안·MCP·코딩 도우미 (수요 큰 키워드)
    ("Google News: MCP Model Context Protocol (KR)", _gnews('"Model Context Protocol" OR "MCP 서버" OR "MCP 클라이언트"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: AI 보안 레드팀 (KR)", _gnews('"AI 레드팀" OR "AI red team" OR "AI 보안 위협" OR "Shadow AI" OR "섀도우 AI"'), "google_news", ["ai-industry", "policy", "domestic"], "ko"),
    ("Google News: AI 에이전트 자동화 (KR)", _gnews('"AI 자동화" OR "에이전트 워크플로우" OR "agent workflow"'), "google_news", ["ai-industry", "domestic"], "ko"),

    # ====================================================================
    # v6.13: 머니투데이 RSS — 직접 RSS 작동 확인됨 (rss.mt.co.kr/mt_news.xml)
    # 나머지 매체는 RSS 미제공 또는 봇 차단 → Google News site: 우회로
    # ====================================================================
    ("머니투데이", "https://rss.mt.co.kr/mt_news.xml", "korean", ["ai-industry", "domestic"], "ko"),

    # v6.13: 검색 의존 한국 매체 → 매체별 Google News 우회 추가
    #   (네이버 검색이 모든 기사를 다 잡아주지 못하므로 site:domain 검색을 보조로)
    ("Google News: 디지털데일리 AI (KR)", _gnews('site:ddaily.co.kr (AI OR "인공지능" OR "리걸테크" OR "거버넌스")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 이데일리 AI (KR)", _gnews('site:edaily.co.kr (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 서울경제 AI (KR)", _gnews('site:sedaily.com (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 파이낸셜뉴스 AI (KR)", _gnews('site:fnnews.com (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 뉴시스 AI (KR)", _gnews('site:newsis.com (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 뉴스1 AI (KR)", _gnews('site:news1.kr (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 헤럴드경제 AI (KR)", _gnews('site:heraldcorp.com (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 더벨 AI (KR)", _gnews('site:thebell.co.kr (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 머니투데이 보조 (KR)", _gnews('site:mt.co.kr (AI OR "인공지능" OR "리걸테크" OR "법무법인") -광고 -이벤트'), "google_news", ["ai-industry", "domestic"], "ko"),

    # ====================================================================
    # v6.14 (2026-05-27): 한국경제 Law&Biz 전용 + 종합지 (사용자 요청)
    # ====================================================================
    # 한국경제 Law&Biz — 직접 RSS 미제공 (404 확인). Google News inurl:lawbiz 우회.
    # 한국경제는 일반 'hankyung.com/feed/it' RSS는 이미 sources.py에 등록되어 있으나
    # Law&Biz 섹션(로펌·변호사·법조)이 별도 카테고리라 site:로 명시적 추가 필요.
    ("Google News: 한국경제 Law&Biz (KR)", _gnews('inurl:hankyung.com/lawbiz OR (site:hankyung.com (로펌 OR 변호사 OR 법조 OR 리걸테크))'), "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: 한국경제 베스트로이어 (KR)", _gnews('site:hankyung.com ("베스트로이어" OR "Best Lawyer" OR "로펌 뉴스")'), "google_news", ["legaltech", "domestic"], "ko"),

    # 종합지 (조선·중앙·동아·한겨레·경향) — RSS 있는 것은 직접, 나머지는 site: 우회
    # 조선일보 IT-Science: RSS 작동 확인 (chosun.com arc outboundfeeds)
    ("조선일보 IT", "https://www.chosun.com/arc/outboundfeeds/rss/category/it-science/?outputType=xml", "korean", ["ai-industry", "domestic"], "ko"),
    # 종합지 site: 우회 — AI/리걸테크 키워드 한정
    ("Google News: 조선일보 AI (KR)", _gnews('site:chosun.com (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 중앙일보 AI (KR)", _gnews('site:joongang.co.kr (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 동아일보 AI (KR)", _gnews('site:donga.com (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 한겨레 AI (KR)", _gnews('site:hani.co.kr (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 경향신문 AI (KR)", _gnews('site:khan.co.kr (AI OR "인공지능" OR "리걸테크" OR "법무법인")'), "google_news", ["ai-industry", "domestic"], "ko"),

    # ====================================================================
    # v6.15.14 (2026-05-28): 사용자 요청 매체·키워드 대폭 확장
    # ====================================================================
    # [A] 직접 RSS 작동 확인된 신규 매체
    # GeekNews 한국 — HN 한국판. AI/오픈소스/개발자 news 풍부. (302 → feedburner)
    ("GeekNews (한국)", "http://feeds.feedburner.com/geeknews-feed", "korean", ["ai-industry", "domestic"], "ko"),
    # Hacker News — 영문 개발자 1차 source. 신기술·오픈소스 발표가 최초로 노출
    ("Hacker News (frontpage)", "https://hnrss.org/frontpage?count=30", "rss", ["ai-industry"], "en"),
    ("Hacker News (AI/ML)", "https://hnrss.org/newest?q=AI+OR+LLM+OR+%22machine+learning%22&count=30", "rss", ["ai-industry"], "en"),
    # 404 Media — AI·디지털 권력 비판적 보도 매체 (전 Vice/Motherboard 기자 창립)
    ("404 Media", "https://www.404media.co/rss/", "rss", ["ai-industry", "policy"], "en"),
    # Platformer — Casey Newton의 빅테크 산업 비평
    ("Platformer (Casey Newton)", "https://www.platformer.news/rss/", "rss", ["ai-industry"], "en"),

    # [B] 한국 매체 site: 우회 추가 (RSS 미제공)
    # 글로벌이코노믹 — 한국 IT/반도체/AI 보도 (Qwen·DeepSeek 동향 보도 활발)
    ("Google News: 글로벌이코노믹 AI (KR)", _gnews('site:g-enews.com (AI OR "인공지능" OR "Qwen" OR "DeepSeek" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    # 동아일보 IT 섹션 — it.donga.com은 별도 호스트라 v6.14 site:donga.com에 안 잡힘
    ("Google News: 동아일보 IT (KR)", _gnews('site:it.donga.com OR (site:donga.com (AI OR "인공지능"))'), "google_news", ["ai-industry", "domestic"], "ko"),
    # 아이뉴스24
    ("Google News: 아이뉴스24 (KR)", _gnews('site:inews24.com (AI OR "인공지능" OR "리걸테크")'), "google_news", ["ai-industry", "domestic"], "ko"),
    # 디지털타임스 IT (기존 게 있긴 한데 보강)
    ("Google News: 디지털타임스 IT (KR)", _gnews('site:dt.co.kr (AI OR "인공지능" OR "법률 AI")'), "google_news", ["ai-industry", "domestic"], "ko"),
    # The Register AI — RSS는 막혔지만 site: 우회로 잡힘
    ("Google News: The Register AI (EN)", _gnews('site:theregister.com (AI OR LLM OR "machine learning")', "en", "US"), "google_news", ["ai-industry"], "en"),

    # [C] 키워드 — 디지털 주권·소버린 AI·오픈소스 LLM·Qwen
    ("Google News: 디지털·데이터 주권 (KR)", _gnews('"디지털 주권" OR "데이터 주권" OR "지식 주권" OR "소버린 AI" OR "sovereign AI"'), "google_news", ["policy", "domestic"], "ko"),
    ("Google News: 오픈소스 LLM 한국 (KR)", _gnews('"오픈소스 AI" OR "오픈소스 LLM" OR "한국어 LLM" OR "K-LLM" OR "오픈웨이트"'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: Qwen 알리바바 (KR)", _gnews('"Qwen" OR "큐원" OR "알리바바 AI" OR "Qwen3"'), "google_news", ["ai-industry", "domestic"], "ko"),

    # [D] GitHub·오픈소스 신규 release — 정식 RSS 없어 Google News 우회 + HN 보조
    ("Google News: GitHub AI 오픈소스 (EN)", _gnews('"github.com" ("released" OR "open source" OR "awesome list") (AI OR LLM OR "machine learning")', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: Hugging Face 신모델 (EN)", _gnews('"Hugging Face" (model OR release OR launched OR trending OR Spaces)', "en", "US"), "google_news", ["ai-industry"], "en"),
    ("Google News: GitHub Trending AI (EN)", _gnews('"trending on GitHub" OR "GitHub trending" (AI OR LLM)', "en", "US"), "google_news", ["ai-industry"], "en"),

    # ====================================================================
    # v6.15.15 (2026-05-28): AI매터스 RSS 추가 (사용자 요청)
    # ====================================================================
    # AI매터스 — 한국 AI 전문 매체. WordPress 표준 RSS 작동 확인.
    # 사용자가 "AI 효과 본 한국 기업 75%, 진짜 강자는 2%" 같은 인사이트
    # 기사를 핵심 가치로 인식.
    ("AI매터스", "https://aimatters.co.kr/feed/", "korean", ["ai-industry", "domestic"], "ko"),

    # ====================================================================
    # v6.15.16 (2026-05-28): DeepSeek 한국어 + AI 모델 가격 인하 키워드
    # ====================================================================
    # 진단: 사이트 데이터에 'DeepSeek' 검색 결과 단 3건, 가격 인하 보도 0건.
    #   딥시크 API 가격 영구 인하 같은 모델 비즈니스 핵심 이벤트가 누락됨.
    # 원인: 한국어 'DeepSeek/딥시크' 전용 검색이 없었음 (영문 'Google News:
    #   DeepSeek (EN)'만 있어서 한국 매체 보도가 누락).
    ("Google News: DeepSeek 딥시크 (KR)", _gnews('"DeepSeek" OR "딥시크" OR "DeepSeek V3" OR "DeepSeek R1" OR "DeepSeek-V"'), "google_news", ["ai-industry", "domestic"], "ko"),
    # AI 모델 가격/요금 정책 — 인하·인상·무료화 등 비즈니스 이벤트
    ("Google News: AI 모델 가격 인하 (KR)", _gnews('("AI" OR "LLM" OR "API") (가격 OR 요금) (인하 OR 인상 OR "무료화" OR "price cut")'), "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: AI Model Pricing (EN)", _gnews('("AI model" OR "LLM" OR "API") ("price cut" OR "price reduc" OR "pricing change" OR "permanent price")', "en", "US"), "google_news", ["ai-industry"], "en"),
    # 보너스 — Frontier model release/announcement (Qwen·DeepSeek·Mistral 등 신모델 + 가격)
    ("Google News: Frontier LLM Release (EN)", _gnews('("DeepSeek" OR "Qwen" OR "Mistral" OR "Llama" OR "Gemini" OR "Claude") (release OR announces OR launches OR "price" OR "open weight")', "en", "US"), "google_news", ["ai-industry"], "en"),
]


def get_active_sources():
    return SOURCES
