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
    # AI 논문 (arXiv API) — papers 카테고리는 여기에서만 부여
    # v2.7: 기존 /rss/ 는 announce-date만 줘서 실제 발행/수정일을 못 잡음 →
    # /api/query 로 교체 (각 entry에 published[v1 제출일] + updated[최신 revision] 정확히 제공)
    # ====================================================================
    ("arXiv cs.AI", "https://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers"], "en"),
    ("arXiv cs.CL", "https://export.arxiv.org/api/query?search_query=cat:cs.CL&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers"], "en"),
    ("arXiv cs.LG", "https://export.arxiv.org/api/query?search_query=cat:cs.LG&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers"], "en"),
    ("arXiv cs.IR", "https://export.arxiv.org/api/query?search_query=cat:cs.IR&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers"], "en"),
    ("arXiv cs.MA (Multi-Agent)", "https://export.arxiv.org/api/query?search_query=cat:cs.MA&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers"], "en"),
    ("arXiv cs.CY (Computers & Society)", "https://export.arxiv.org/api/query?search_query=cat:cs.CY&max_results=30&sortBy=lastUpdatedDate&sortOrder=descending", "arxiv", ["papers", "policy"], "en"),
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
    ("Google News: Multi-agent System (EN)", _gnews('"multi-agent" OR "multiagent system" OR "agent infrastructure"', "en", "US"), "google_news", ["ai-industry"], "en"),
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
]


def get_active_sources():
    return SOURCES
