"""
AI & Legaltech Watch — 소스 카탈로그

데이터 소스를 한 곳에서 관리합니다.

각 소스: (name, url, source_type, default_categories, lang)
- source_type: rss / arxiv / korean / blog
  ★ papers 카테고리는 arxiv 타입에만 부여
"""

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
    ("디일렉", "https://www.thelec.kr/rss/allArticle.xml", "korean", ["ai-industry", "domestic"], "ko"),
    ("플래텀 (스타트업)", "https://platum.kr/feed", "korean", ["ai-industry", "domestic", "funding"], "ko"),
    ("벤처스퀘어", "https://www.venturesquare.net/feed", "korean", ["domestic", "funding"], "ko"),
    # 더밀크 RSS 실패 → Google News 우회
    ("더밀크", "https://news.google.com/rss/search?q=site%3Athemiilk.com+OR+%22%EB%8D%94%EB%B0%80%ED%81%AC%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("매일경제 IT", "https://www.mk.co.kr/rss/30000023/", "korean", ["domestic"], "ko"),
    ("한국경제 IT", "https://www.hankyung.com/feed/it", "korean", ["domestic"], "ko"),

    # ====================================================================
    # Google News RSS — 키워드 기반 (강력한 광범위 커버리지)
    # 패턴: https://news.google.com/rss/search?q={keyword}&hl={lang}&gl={country}&ceid={country}:{lang}
    # ====================================================================
    # 한국어 — 리걸테크 핵심
    ("Google News: 리걸테크 (KR)", "https://news.google.com/rss/search?q=%EB%A6%AC%EA%B1%B8%ED%85%8C%ED%81%AC+OR+%EB%B2%95%EB%A5%A0AI&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: BHSN·로앤컴퍼니 (KR)", "https://news.google.com/rss/search?q=BHSN+OR+%EB%A1%9C%EC%95%A4%EC%BB%B4%ED%8D%BC%EB%8B%88+OR+%EB%A1%9C%EC%95%A4%EA%B5%BF&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: AI 산업 (KR)", "https://news.google.com/rss/search?q=%22AI+%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8%22+OR+%22%EC%83%9D%EC%84%B1AI%22+OR+%22Claude%22+OR+%22OpenAI%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: AI 규제·정책 (KR)", "https://news.google.com/rss/search?q=%22AI+%EA%B7%9C%EC%A0%9C%22+OR+%22AI+%EA%B8%B0%EB%B3%B8%EB%B2%95%22+OR+%22EU+AI+Act%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["policy", "domestic"], "ko"),

    # 영문 — 리걸테크 회사명별
    ("Google News: Harvey AI (EN)", "https://news.google.com/rss/search?q=%22Harvey+AI%22+OR+%22Harvey.ai%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Legora (EN)", "https://news.google.com/rss/search?q=%22Legora%22+legal&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Mike·Hebbia·Ironclad (EN)", "https://news.google.com/rss/search?q=%22Mike+OSS%22+OR+%22Hebbia%22+OR+%22Ironclad%22+OR+%22Spellbook%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Law firm AI (EN)", "https://news.google.com/rss/search?q=%22law+firm+AI%22+OR+%22BigLaw+AI%22+OR+%22legal+AI+adoption%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),

    # 영문 — AI 산업
    ("Google News: AI Frontier Labs (EN)", "https://news.google.com/rss/search?q=%22Anthropic%22+OR+%22OpenAI%22+OR+%22DeepMind%22+OR+%22Mistral%22+announces+OR+launches&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: AI Agents (EN)", "https://news.google.com/rss/search?q=%22AI+agent%22+OR+%22autonomous+agent%22+OR+%22multi-agent%22+launches+OR+benchmark&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: AI Funding (EN)", "https://news.google.com/rss/search?q=%22AI+startup%22+raises+OR+%22Series+B%22+OR+%22valuation%22+legal+OR+enterprise&hl=en&gl=US&ceid=US:en", "google_news", ["funding"], "en"),
    ("Google News: AI Regulation (EN)", "https://news.google.com/rss/search?q=%22AI+regulation%22+OR+%22AI+governance%22+OR+%22EU+AI+Act%22&hl=en&gl=US&ceid=US:en", "google_news", ["policy"], "en"),

    # ====================================================================
    # v2.7 추가 — 실무자 관점 확장 키워드
    # 단순 산업 동향이 아닌 'AI 도입·시장 구도·실무 적용' 시각 강화
    # ====================================================================
    # 한국 — AI 도입·활용·전환
    ("Google News: AI 도입·전환 (KR)", "https://news.google.com/rss/search?q=%22AI+%EB%8F%84%EC%9E%85%22+OR+%22AI+%ED%99%9C%EC%9A%A9+%EC%82%AC%EB%A1%80%22+OR+%22AI+%EC%A0%84%ED%99%98%22+OR+%22%EC%82%AC%EB%82%B4+AI%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 엔터프라이즈 AI (KR)", "https://news.google.com/rss/search?q=%22%EC%97%94%ED%84%B0%ED%94%84%EB%9D%BC%EC%9D%B4%EC%A6%88+AI%22+OR+%22%EA%B8%B0%EC%97%85%EC%9A%A9+AI%22+OR+%22%EC%97%85%EB%AC%B4+%EC%9E%90%EB%8F%99%ED%99%94%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["ai-industry", "domestic"], "ko"),
    ("Google News: 로펌·법무법인 AI (KR)", "https://news.google.com/rss/search?q=(%22%EB%A1%9C%ED%8E%8C+AI%22+OR+%22%EB%B2%95%EB%AC%B4%EB%B2%95%EC%9D%B8+AI%22+OR+%22%EB%B3%80%ED%98%B8%EC%82%AC+AI%22+OR+%22%EA%B3%84%EC%95%BD%EC%84%9C+AI%22)&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["legaltech", "domestic"], "ko"),
    ("Google News: AI 컴플라이언스 (KR)", "https://news.google.com/rss/search?q=%22AI+%EC%BB%B4%ED%94%8C%EB%9D%BC%EC%9D%B4%EC%96%B8%EC%8A%A4%22+OR+%22AI+%EA%B0%80%EC%9D%B4%EB%93%9C%EB%9D%BC%EC%9D%B8%22+OR+%22AI+%EC%9C%A4%EB%A6%AC%22+OR+%22%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4+AI%22&hl=ko&gl=KR&ceid=KR:ko", "google_news", ["policy", "domestic"], "ko"),

    # 영문 — 계약서/실무 use case + 오픈소스 + 시장 구도
    ("Google News: Contract & Legal AI Use Cases (EN)", "https://news.google.com/rss/search?q=%22contract+AI%22+OR+%22contract+review+AI%22+OR+%22due+diligence+AI%22+OR+%22legal+research+AI%22&hl=en&gl=US&ceid=US:en", "google_news", ["legaltech"], "en"),
    ("Google News: Open-source LLM (EN)", "https://news.google.com/rss/search?q=%22open-source+LLM%22+OR+%22open+source+language+model%22+OR+%22Llama%22+OR+%22DeepSeek%22+OR+%22vLLM%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
    ("Google News: Build vs Buy AI (EN)", "https://news.google.com/rss/search?q=%22build+vs+buy+AI%22+OR+%22in-house+AI%22+OR+%22vendor+lock-in%22+OR+%22AI+ROI%22+OR+%22AI+cost%22&hl=en&gl=US&ceid=US:en", "google_news", ["ai-industry"], "en"),
]


def get_active_sources():
    return SOURCES
