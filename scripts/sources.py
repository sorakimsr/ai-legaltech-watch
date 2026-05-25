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
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml", "rss", ["ai-industry", "product"], "en"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/", "rss", ["ai-industry", "product"], "en"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml", "rss", ["ai-industry"], "en"),
    ("Google Research", "https://research.google/blog/rss/", "rss", ["ai-industry"], "en"),
    ("Meta AI Blog", "https://ai.meta.com/blog/rss/", "rss", ["ai-industry", "product"], "en"),
    ("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/", "rss", ["ai-industry", "product"], "en"),
    ("NVIDIA Blog", "https://blogs.nvidia.com/feed/", "rss", ["ai-industry"], "en"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "rss", ["ai-industry"], "en"),
    ("Mistral AI Blog", "https://mistral.ai/news/feed.xml", "rss", ["ai-industry", "product"], "en"),
    ("Stability AI", "https://stability.ai/news?format=rss", "rss", ["ai-industry", "product"], "en"),
    ("Perplexity Blog", "https://www.perplexity.ai/blog/rss.xml", "rss", ["ai-industry", "product"], "en"),

    # ====================================================================
    # AI 뉴스 매체 (영문)
    # ====================================================================
    ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "rss", ["ai-industry"], "en"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "rss", ["ai-industry"], "en"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "rss", ["ai-industry"], "en"),
    ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "rss", ["ai-industry"], "en"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss", "rss", ["ai-industry"], "en"),
    ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab", "rss", ["ai-industry"], "en"),
    ("Axios AI", "https://api.axios.com/feed/", "rss", ["ai-industry"], "en"),
    ("The Information AI", "https://www.theinformation.com/feed", "rss", ["ai-industry"], "en"),
    ("Semianalysis", "https://www.semianalysis.com/feed", "rss", ["ai-industry"], "en"),
    ("The Decoder", "https://the-decoder.com/feed/", "rss", ["ai-industry"], "en"),
    ("Import AI (Jack Clark)", "https://importai.substack.com/feed", "blog", ["ai-industry"], "en"),
    ("Ben's Bites", "https://bensbites.beehiiv.com/feed", "blog", ["ai-industry"], "en"),
    ("The Batch (DeepLearning.AI)", "https://www.deeplearning.ai/the-batch/feed/", "blog", ["ai-industry"], "en"),
    ("AI Snake Oil", "https://www.aisnakeoil.com/feed", "blog", ["ai-industry", "policy"], "en"),
    ("Marginal Revolution AI", "https://marginalrevolution.com/marginalrevolution/category/economics/artificial-intelligence/feed", "blog", ["ai-industry"], "en"),
    ("Last Week in AI", "https://lastweekin.ai/feed", "blog", ["ai-industry"], "en"),

    # ====================================================================
    # 리걸테크 (영문)
    # ====================================================================
    ("Artificial Lawyer", "https://www.artificiallawyer.com/feed/", "rss", ["legaltech"], "en"),
    ("Legal IT Insider", "https://legaltechnology.com/feed/", "rss", ["legaltech"], "en"),
    ("Legal Cheek", "https://www.legalcheek.com/feed/", "rss", ["legaltech"], "en"),
    ("LawSites (Bob Ambrogi)", "https://www.lawnext.com/feed", "rss", ["legaltech"], "en"),
    ("ABA Journal Tech", "https://www.abajournal.com/topic/legal_technology/feed", "rss", ["legaltech"], "en"),
    ("Above the Law", "https://abovethelaw.com/feed/", "rss", ["legaltech"], "en"),
    ("Law.com Legal Tech", "https://www.law.com/legaltechnews/feed/", "rss", ["legaltech"], "en"),
    ("Legal Futures", "https://www.legalfutures.co.uk/feed", "rss", ["legaltech"], "en"),
    ("Global Legal Post", "https://www.globallegalpost.com/feed/", "rss", ["legaltech"], "en"),
    ("Stanford CodeX", "https://law.stanford.edu/codex-the-stanford-center-for-legal-informatics/feed/", "rss", ["legaltech"], "en"),
    ("Harvey Blog", "https://www.harvey.ai/blog/rss.xml", "rss", ["legaltech", "product"], "en"),
    ("Legora Blog", "https://legora.com/blog/rss.xml", "rss", ["legaltech", "product"], "en"),

    # ====================================================================
    # AI 논문 (arXiv) — papers 카테고리는 여기에서만 부여
    # ====================================================================
    ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI", "arxiv", ["papers"], "en"),
    ("arXiv cs.CL", "http://export.arxiv.org/rss/cs.CL", "arxiv", ["papers"], "en"),
    ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG", "arxiv", ["papers"], "en"),
    ("arXiv cs.IR", "http://export.arxiv.org/rss/cs.IR", "arxiv", ["papers"], "en"),
    ("arXiv cs.MA (Multi-Agent)", "http://export.arxiv.org/rss/cs.MA", "arxiv", ["papers"], "en"),
    ("arXiv cs.CY (Computers & Society)", "http://export.arxiv.org/rss/cs.CY", "arxiv", ["papers", "policy"], "en"),
    ("Papers With Code", "https://paperswithcode.com/latest/feed.xml", "arxiv", ["papers"], "en"),

    # ====================================================================
    # 국내 매체 (한국어)
    # ====================================================================
    ("AI타임스", "https://www.aitimes.com/rss/allArticle.xml", "korean", ["ai-industry", "domestic"], "ko"),
    ("AI타임스 (정책)", "https://www.aitimes.com/rss/S1N2.xml", "korean", ["policy", "domestic"], "ko"),
    ("법률신문 (테크)", "https://www.lawtimes.co.kr/rss/CategoryRss.aspx?serial=1004", "korean", ["legaltech", "domestic"], "ko"),
    ("법률신문 (전체)", "https://www.lawtimes.co.kr/rss/totalRss.aspx", "korean", ["domestic"], "ko"),
    ("ZDNet Korea", "https://feeds.feedburner.com/zdkorea", "korean", ["ai-industry", "domestic"], "ko"),
    ("디지털타임스 IT", "https://www.dt.co.kr/rss/section_rss.xml?section=S1N3", "korean", ["ai-industry", "domestic"], "ko"),
    ("전자신문 AI", "https://rss.etnews.com/Section902.xml", "korean", ["ai-industry", "domestic"], "ko"),
    ("바이라인네트워크", "https://byline.network/feed/", "korean", ["ai-industry", "domestic"], "ko"),
    ("디일렉", "https://www.thelec.kr/rss/allArticle.xml", "korean", ["ai-industry", "domestic"], "ko"),
    ("플래텀 (스타트업)", "https://platum.kr/feed", "korean", ["ai-industry", "domestic", "funding"], "ko"),
    ("벤처스퀘어", "https://www.venturesquare.net/feed", "korean", ["domestic", "funding"], "ko"),
    ("더밀크", "https://www.themiilk.com/rss", "korean", ["ai-industry", "domestic"], "ko"),
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
]


def get_active_sources():
    return SOURCES
