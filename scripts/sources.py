"""
AI & Legaltech Watch — 소스 카탈로그

데이터 소스를 한 곳에서 관리합니다. 여기에 새 항목 추가만 하면 됩니다.

각 소스는 다음 필드로 구성됩니다:
- name: 표시 이름
- url: RSS/Atom 피드 URL
- source_type: rss / arxiv / korean / blog
- default_categories: 기본 카테고리 (자동 분류 외 추가)
- lang: en / ko
"""

SOURCES = [
    # ====================================================================
    # 글로벌 AI 산업 (영문)
    # ====================================================================
    ("OpenAI Blog", "https://openai.com/blog/rss.xml", "rss", ["ai-industry", "product"], "en"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml", "rss", ["ai-industry", "product"], "en"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/", "rss", ["ai-industry", "product"], "en"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml", "rss", ["ai-industry", "papers"], "en"),
    ("Google Research", "https://research.google/blog/rss/", "rss", ["ai-industry", "papers"], "en"),
    ("Meta AI Blog", "https://ai.meta.com/blog/rss/", "rss", ["ai-industry", "product"], "en"),
    ("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/", "rss", ["ai-industry", "product"], "en"),
    ("NVIDIA Blog", "https://blogs.nvidia.com/feed/", "rss", ["ai-industry"], "en"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "rss", ["ai-industry", "papers"], "en"),
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
    ("Stanford Center for Legal Informatics", "https://law.stanford.edu/codex-the-stanford-center-for-legal-informatics/feed/", "rss", ["legaltech", "papers"], "en"),
    ("Harvey Blog", "https://www.harvey.ai/blog/rss.xml", "rss", ["legaltech", "product"], "en"),
    ("Legora Blog", "https://legora.com/blog/rss.xml", "rss", ["legaltech", "product"], "en"),

    # ====================================================================
    # AI 논문 (arXiv)
    # ====================================================================
    ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI", "arxiv", ["papers"], "en"),
    ("arXiv cs.CL", "http://export.arxiv.org/rss/cs.CL", "arxiv", ["papers"], "en"),
    ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG", "arxiv", ["papers"], "en"),
    ("arXiv cs.IR", "http://export.arxiv.org/rss/cs.IR", "arxiv", ["papers"], "en"),
    ("arXiv cs.MA (Multi-Agent)", "http://export.arxiv.org/rss/cs.MA", "arxiv", ["papers"], "en"),
    ("arXiv cs.CY (Computers & Society)", "http://export.arxiv.org/rss/cs.CY", "arxiv", ["papers", "policy"], "en"),
    ("Papers With Code", "https://paperswithcode.com/latest/feed.xml", "rss", ["papers"], "en"),

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
]


def get_active_sources():
    """모든 소스 반환"""
    return SOURCES
