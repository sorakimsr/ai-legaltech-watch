// AI & Legaltech Watch v2.7 — 다중선택 + AI 분석 + 시계열 + 7일 추이

// 강제 HTTPS — Mixed Content 차단으로 worker fetch가 실패하는 문제 방지
// (http:// 로 접속한 사용자는 https:// 로 즉시 redirect)
if (location.protocol === 'http:' && !location.hostname.startsWith('localhost') && !location.hostname.startsWith('127.0.0.1')) {
  location.replace(location.href.replace(/^http:/, 'https:'));
}

// ============================================================================
// AI 분석 백엔드 (Cloudflare Worker)
// ============================================================================
const WORKER_ENDPOINT = "https://daibfy-ai-proxy.sora-kim-sr.workers.dev/analyze";

// 백엔드별 모델 옵션 (worker의 ALLOWED_MODELS와 동기화)
const MODELS = {
  openai: [
    { id: "gpt-4o-mini", label: "GPT-4o-mini · 빠름·저렴 (기본)", hint: "토큰당 $0.00015 / $0.00060 (입·출력)" },
    { id: "gpt-4o", label: "GPT-4o · 균형", hint: "토큰당 $0.0025 / $0.010" },
    { id: "gpt-4-turbo", label: "GPT-4 Turbo · 이전 강력형", hint: "토큰당 $0.010 / $0.030" },
    { id: "o1", label: "o1 · 깊은 추론", hint: "토큰당 $0.015 / $0.060, 느림" },
    { id: "o1-mini", label: "o1-mini · 추론·저렴", hint: "토큰당 $0.003 / $0.012" },
  ],
  claude: [
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 · 균형 (기본)", hint: "토큰당 $3 / $15 per MTok" },
    { id: "claude-opus-4-6", label: "Claude Opus 4.6 · 최강", hint: "토큰당 $15 / $75 per MTok, 가장 정확" },
    { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 · 가장 빠름", hint: "토큰당 $1 / $5 per MTok" },
    { id: "claude-3-7-sonnet-latest", label: "Claude 3.7 Sonnet · 이전 세대", hint: "이전 세대 균형 모델" },
    { id: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku · 이전 빠름", hint: "이전 세대 빠른 모델" },
  ],
};

const PROMPT_PRESETS = {
  summary:
    "다음 뉴스들의 핵심을 3~5개의 불릿 포인트로 요약해주세요. 각 포인트는 한 문장으로, 구체적 사실(회사명·금액·날짜) 중심으로.",
  insights:
    "다음 뉴스들을 한국의 전략·기획·AI 업무 담당자 관점에서 분석해주세요. (1) 흐름 정리 (2) 의미와 영향 (3) 본인 업무에 적용할 액션 가능한 시사점 3가지.",
  trends:
    "다음 뉴스들에서 반복되는 패턴·키워드·플레이어를 추출해 트렌드 분석해주세요. 강한 시그널과 약한 시그널을 구분하고, 향후 3~6개월 내 추적할 가치 있는 변수를 제시.",
  competitive:
    "다음 뉴스들에 등장하는 회사·제품·플랫폼을 경쟁 구도로 정리해주세요. 표 형식으로 비교 (강점·약점·차별화 요소), 시장 포지셔닝 분석, 잠재적 통합·M&A 가능성.",
  opportunity:
    "다음 뉴스들이 시사하는 한국 시장 진출/협업 기회를 분석해주세요. (1) 글로벌 흐름 (2) 한국 시장의 갭과 기회 (3) 진입 전략·파트너십 아이디어.",
  custom: "",
};

const state = {
  data: null,
  history: null,        // strategy_history.json
  sourceHistory: null,  // source_history.json
  // v3.11: 진입 시 첫 페이지 = 시사점 daily (사용자 정책)
  view: 'strategy',     // strategy | latest | top | today | sources | saved | papers | analyses
  // 시사점 sub-state
  strategyPeriod: 'daily',  // daily | weekly | monthly
  strategyKey: null,        // 선택된 날짜·주·월 키
  // v2.7.1: 논문 흐름 sub-state — v4.1: daily 디폴트
  papersPeriod: 'daily',    // daily | weekly | monthly
  papersKey: null,          // 선택된 날짜·주·월 키
  paperTrendsHistory: null, // paper_trends_history.json
  // 소스 sub-state
  sourcesTab: 'status',     // status | trend
  sourcesPeriod: '7days',   // today | 7days | 30days | all (소스 현황 표용)
  trendView: 'source',      // source | category (7일 추이 차트 모드)
  // 필터 — v2.8.3: 카테고리 OR 다중 선택 (Set)
  category: 'all',  // legacy 단일 선택 호환 (UI 표시 한 줄에 사용)
  categories: new Set(['all']),  // 실제 필터 적용용 다중 선택
  search: '',
  // v3.11: 뉴스 피드 디폴트 기간 = 오늘 (사용자 정책)
  dateFilter: 'today',
  // v6.15.26 (2026-05-29): 특정 일자 필터 — dateFilter='specific'일 때 사용 (YYYY-MM-DD)
  specificDate: '',
  langFilter: 'all',
  // v2.7.1: 정렬 기준 (뉴스 피드 통합 후) — latest | score | today
  // v3.11: 디폴트 = 중요도 (사용자 정책)
  sortBy: 'score',
  // chart instance
  trendChart: null,
  // 다중 선택 — 뉴스 카드(URL 기반) + 시사점 trend 카드(cardKey 기반)
  selectedUrls: new Set(),
  selectedTrends: new Set(),  // v3.0: trend cardKey 집합 — AI 분석 시 trend 본문+근거 기사 포함
  // 분석 모달 상태
  analyzeBackend: "openai",
  analyzeModel: "gpt-4o-mini",
  analyzePromptPreset: "summary",
  // v2.7: 사용자 저장 항목 (localStorage 동기화)
  saved: { items: {}, strategy: {} },  // {url: true}, {strategyKey: {card data}}
  // v2.7.7: 저장한 항목 페이지의 활성 탭 — insights | news
  savedTab: 'insights',
  // v2.7.5: AI 분석 결과 history (localStorage)
  analyses: [],  // [{id, timestamp, backend, model, prompt, items: [{title,url,source,date}], result}]
  // Phase 2b: 엔티티 데이터 (data/entities.json fetch)
  entities: null,           // {entities: {id: {...}}, generated_at, total_entities}
  selectedEntityId: null,   // 상세 화면용
  // Phase 3: LLM 관계 데이터 (data/relations.json fetch)
  relations: null,                // {relations: [...], generated_at, total_relations}
  relationsByEntity: null,        // {entityId: [{otherId, type, dir, evidence, weight, source_type}, ...]}
  graphTypeFilter: null,          // 그래프 뷰 필터: null | relation type (e.g. 'competes_with')
  // v5.0: 엔티티/그래프 옵션
  entityIncludePapers: true,      // 엔티티 카운트·노드 크기 계산 시 논문 흐름 포함
  graphShowIsolated: false,       // 지식그래프에서 관계 없는 엔티티도 표시
};

const ANALYSES_STORAGE_KEY = 'daibfy_analyses_v1';

function loadAnalyses() {
  try {
    const raw = localStorage.getItem(ANALYSES_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) state.analyses = parsed;
    }
  } catch (e) {}
}

function persistAnalyses() {
  try {
    localStorage.setItem(ANALYSES_STORAGE_KEY, JSON.stringify(state.analyses));
  } catch (e) {}
}

function saveAnalysis(entry) {
  // 최대 50개 보관 (오래된 것부터 제거)
  state.analyses.unshift(entry);
  if (state.analyses.length > 50) state.analyses = state.analyses.slice(0, 50);
  persistAnalyses();
}

function deleteAnalysis(id) {
  state.analyses = state.analyses.filter(a => a.id !== id);
  persistAnalyses();
}

// ===== 저장(북마크) 기능 =====
const SAVED_STORAGE_KEY = 'daibfy_saved_v1';

function loadSaved() {
  try {
    const raw = localStorage.getItem(SAVED_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      state.saved = { items: parsed.items || {}, strategy: parsed.strategy || {} };
    }
  } catch (e) {}
}

function persistSaved() {
  try {
    localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(state.saved));
  } catch (e) {}
}

function isSaved(kind, key) {
  return !!(state.saved[kind] || {})[key];
}

// v2.7.4: 저장 시점(timestamp) 반환 — 이전 boolean 데이터도 호환
function getSavedAt(kind, key) {
  const entry = (state.saved[kind] || {})[key];
  if (!entry) return 0;
  if (typeof entry === 'object' && entry.savedAt) return entry.savedAt;
  return 1;  // legacy boolean → 가장 옛날로 정렬
}

function toggleSaved(kind, key, value) {
  if (!state.saved[kind]) state.saved[kind] = {};
  if (isSaved(kind, key)) {
    delete state.saved[kind][key];
  } else {
    // v2.7.4: 저장 시 timestamp 기록. value가 객체면 savedAt 추가, 아니면 {savedAt} 만 저장
    const now = Date.now();
    if (value && typeof value === 'object') {
      state.saved[kind][key] = { ...value, savedAt: now };
    } else {
      state.saved[kind][key] = { savedAt: now };
    }
  }
  persistSaved();
}

function makeStrategyKey(period, dateKey, card) {
  // 같은 일자·주기 내 카드 식별자: tag 또는 title 해시
  return `${period}|${dateKey || ''}|${(card.tag || card.title || '').slice(0, 80)}`;
}

// v6.0 (P2-3): escapeAttr / escapeHtml / escapeHtmlWithMark / formatKoreanDate /
//              isNewToday / cssEscape / renderMarkdown / unboldProperNouns / UNBOLD_PROPER_NOUNS /
//              _escapeRegex / PAPERS_NARRATIVE_LABELS 는 app.util.js로 분리되었습니다.

// ============================================================================
// v6.5: URL routing — path-based + sub-state 포함
// /insights, /newsfeeds, /papers, /bookmarks, /analysis,
// /entities, /graph, /sources_status, /sources_trends
// + /insights/<period>/<key>, /papers/<period>/<key>
// key 형식: daily=YYYYMMDD, weekly=YYYYWxx, monthly=YYYYMM
// ============================================================================

// internal state.view ↔ URL slug
const VIEW_TO_URL = {
  strategy: 'insights',
  latest:   'newsfeeds',
  papers:   'papers',
  saved:    'bookmarks',
  analyses: 'analysis',
  entities: 'entities',
  graph:    'graph',
  // sources는 sourcesTab에 따라 status/trends로 분기
};
const URL_TO_VIEW = {
  insights:       { view: 'strategy' },
  newsfeeds:      { view: 'latest' },
  papers:         { view: 'papers' },
  bookmarks:      { view: 'saved' },
  analysis:       { view: 'analyses' },
  entities:       { view: 'entities' },
  graph:          { view: 'graph' },
  sources_status: { view: 'sources', sourcesTab: 'status' },
  sources_trends: { view: 'sources', sourcesTab: 'trend' },
};

// state key (ISO) ↔ URL slug (YYYYMMDD / YYYYWxx / YYYYMM)
function isoKeyToUrl(isoKey) {
  if (!isoKey) return '';
  return String(isoKey).replace(/-/g, '');
}
function urlKeyToIso(urlKey, period) {
  if (!urlKey) return null;
  if (period === 'daily' && /^\d{8}$/.test(urlKey)) {
    return `${urlKey.slice(0,4)}-${urlKey.slice(4,6)}-${urlKey.slice(6,8)}`;
  }
  if (period === 'weekly' && /^\d{4}W\d{2}$/.test(urlKey)) {
    return `${urlKey.slice(0,4)}-W${urlKey.slice(5)}`;
  }
  if (period === 'monthly' && /^\d{6}$/.test(urlKey)) {
    return `${urlKey.slice(0,4)}-${urlKey.slice(4,6)}`;
  }
  return urlKey;
}

// URL → state partial 추출 (init 및 popstate에서 사용)
function parseUrlToState(pathname) {
  const parts = (pathname || '/').split('/').filter(Boolean);
  if (parts.length === 0) return { view: 'strategy' };
  const head = parts[0];
  const mapped = URL_TO_VIEW[head];
  if (!mapped) return { view: 'strategy' };  // unknown path → default
  const result = { ...mapped };
  // sub-state: /insights/<period>/<key>, /papers/<period>/<key>
  if ((head === 'insights' || head === 'papers') && parts.length >= 2) {
    const period = parts[1];
    if (['daily', 'weekly', 'monthly'].includes(period)) {
      if (head === 'insights') {
        result.strategyPeriod = period;
        result.strategyKey = parts.length >= 3 ? urlKeyToIso(parts[2], period) : null;
      } else {
        result.papersPeriod = period;
        result.papersKey = parts.length >= 3 ? urlKeyToIso(parts[2], period) : null;
      }
    }
  }
  return result;
}

// state → URL 생성 (view 전환 시 pushState용)
function buildUrlFromState() {
  if (state.view === 'sources') {
    return state.sourcesTab === 'trend' ? '/sources_trends' : '/sources_status';
  }
  const slug = VIEW_TO_URL[state.view];
  if (!slug) return '/';
  let url = `/${slug}`;
  if (state.view === 'strategy' && state.strategyPeriod) {
    url += `/${state.strategyPeriod}`;
    if (state.strategyKey) url += `/${isoKeyToUrl(state.strategyKey)}`;
  } else if (state.view === 'papers' && state.papersPeriod) {
    url += `/${state.papersPeriod}`;
    if (state.papersKey) url += `/${isoKeyToUrl(state.papersKey)}`;
  }
  return url;
}

// URL sync — state 변경 후 호출하면 browser URL 갱신
function syncUrl(replace = false) {
  const newUrl = buildUrlFromState();
  const current = window.location.pathname;
  if (current === newUrl) return;
  try {
    if (replace) history.replaceState({ view: state.view }, '', newUrl);
    else history.pushState({ view: state.view }, '', newUrl);
  } catch (e) { /* security or unsupported — ignore */ }
}

const CATEGORIES = [
  { id: 'all', label: '전체' },
  { id: 'legaltech', label: '리걸테크' },
  { id: 'papers', label: 'AI 논문' },
  { id: 'models', label: '모델·벤치마크' },           // v6.15.17: DeepSeek/Qwen/Gemma/가격·release
  { id: 'coding', label: 'AI 코딩' },                  // v6.15.17: Cursor/Copilot/Windsurf
  { id: 'infra', label: 'AI 인프라' },                 // v6.15.17: Groq/Cerebras/GPU/sLLM
  { id: 'product', label: '제품·기능' },
  { id: 'funding', label: '투자·M&A' },
  { id: 'adoption', label: '도입사례' },
  { id: 'governance', label: 'AI 거버넌스·리스크' },  // v3.0: 사내 거버넌스·리스크·평가
  { id: 'gov_policy', label: '정부 동향' },           // v6.7: 중앙정부 부처 AI 정책
  { id: 'policy', label: '정책·규제' },
  { id: 'market', label: '시장·경쟁' },               // v3.0: 시장 구조·벤더 종속·모트
  { id: 'ai-industry', label: 'AI 산업 (기타)' },     // fallback
];

const VIEW_META = {
  latest:    { title: '뉴스 피드', hint: '정렬·기간·언어 필터로 자유 탐색' },
  // 백워드 호환: 구 url/링크가 top, today를 가리킬 경우 latest로 매핑
  top:       { title: '뉴스 피드', hint: '중요도순으로 정렬됨' },
  today:     { title: '뉴스 피드', hint: '오늘 추가된 항목만' },
  strategy:  { title: '시사점', hint: 'Daily/Weekly/Monthly로 LLM 자동 생성' },
  papers:    { title: 'AI 논문 흐름', hint: 'Daily/Weekly/Monthly 시계열 분석' },
  sources:   { title: '소스 현황', hint: '활성·유휴·오류 + 7일 추이' },
  saved:     { title: '저장한 항목', hint: '북마크한 시사점·뉴스 카드' },
  analyses:  { title: 'AI 분석 결과', hint: '이전에 실행한 AI 분석 세션 기록' },
  entities:  { title: '엔티티', hint: 'AI 회사·로펌·정부 부처·정책·기술 등 추적 — 클릭하면 관련 article·시사점·논문' },
  graph:     { title: '지식그래프', hint: '엔티티 간 관계 (경쟁·제휴·도입·규제·인수·투자) — 시사점 카드에서 LLM이 추출' },
};

async function init() {
  loadSaved();  // v2.7: localStorage 북마크 복원
  loadAnalyses();  // v2.7.5: AI 분석 결과 history 복원

  // v6.5: URL → state 초기화. 새로고침·북마크·공유 시 해당 view로 바로 진입.
  const fromUrl = parseUrlToState(window.location.pathname);
  Object.assign(state, fromUrl);
  // popstate: 브라우저 뒤로/앞으로 가기 시 state 복원
  window.addEventListener('popstate', () => {
    const restored = parseUrlToState(window.location.pathname);
    Object.assign(state, restored);
    // active 표시 갱신
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.nav-sub').forEach(n => n.classList.remove('active'));
    const slug = state.view === 'sources'
      ? (state.sourcesTab === 'trend' ? 'sources_trends' : 'sources_status')
      : VIEW_TO_URL[state.view];
    const navEl = document.querySelector(`.nav-item[href$="/${slug}"]`)
      || document.querySelector(`.nav-item[data-view="${state.view}"]`);
    if (navEl) navEl.classList.add('active');
    if (typeof renderContent === 'function') renderContent();
  });

  // v6.0 (P2-1): cache-buster를 빌드 타임스탬프로 교체.
  //   1) data/version.json (~30byte)만 no-cache로 가져와 빌드 버전 확인.
  //   2) 큰 파일(news.json 등)은 ?v=<build> 로 가져와 CDN/브라우저 캐시 활용.
  //   3) 빌드가 갱신되면 ?v= 값이 바뀌어 새 파일을 가져오고, 그 사이엔 캐시 hit.
  //   이전 동작은 ?t=Date.now()로 매 로드마다 1.1MB news.json을 강제 재다운로드했음.
  let buildVersion = String(Date.now());  // version.json 없을 때 안전한 fallback
  try {
    const vr = await fetch('./data/version.json', { cache: 'no-cache' });
    if (vr.ok) {
      const v = await vr.json();
      buildVersion = v.build || v.last_updated || buildVersion;
    }
  } catch (e) { /* version.json은 옵션 — 없어도 동작 */ }
  state.buildVersion = buildVersion;  // loadEntities/loadRelations 등에서 공유

  const versionedFetch = (path) =>
    fetch(path + '?v=' + encodeURIComponent(buildVersion), { cache: 'default' });

  try {
    const res = await versionedFetch('./data/news.json');
    state.data = await res.json();
  } catch (e) {
    console.error('news.json 로드 실패:', e);
    state.data = { items: [], strategy: [], sources: [], stats: {} };
  }

  // 보조 데이터 (옵션)
  try {
    const r = await versionedFetch('./data/strategy_history.json');
    state.history = await r.json();
  } catch (e) {
    state.history = { daily: {}, weekly: {}, monthly: {} };
  }
  try {
    const r = await versionedFetch('./data/source_history.json');
    state.sourceHistory = await r.json();
  } catch (e) {
    state.sourceHistory = {};
  }
  try {
    const r = await versionedFetch('./data/paper_trends.json');
    state.paperTrends = await r.json();
  } catch (e) {
    state.paperTrends = null;
  }
  // v2.7.1: 논문 시계열 history (선택 사항 — 없으면 paper_trends만 표시)
  try {
    const r = await versionedFetch('./data/paper_trends_history.json');
    state.paperTrendsHistory = await r.json();
  } catch (e) {
    state.paperTrendsHistory = null;
  }

  renderTopbar();
  renderStats();
  renderCategoryBar();
  renderContent();
  bindEvents();
}

function renderTopbar() {
  const last = state.data.last_updated;
  const el = document.getElementById('last-updated-text');
  if (last) {
    el.textContent = `최근 갱신: ${formatKoreanDate(new Date(last))} · 매일 KST 06:00 자동`;
  }
  const buildInfo = document.getElementById('last-build-info');
  if (state.data.build_count) {
    buildInfo.textContent = `Build #${state.data.build_count} · © 2026`;
  }
}

function renderStats() {
  const row = document.getElementById('stat-row');
  // v2.7.3: stat-row는 소스 현황 view에서만 표시. 다른 view에서는 숨김.
  if (state.view !== 'sources') {
    row.style.display = 'none';
    return;
  }
  row.style.display = 'grid';

  // v3.0: 6개 카드를 state.sourcesPeriod(today/7days/30days/all)에 따라 동적 계산
  // — 하단 표와 동일한 기준(source_history의 'new' 합산)을 사용해 일치성 확보.
  const period = state.sourcesPeriod || '7days';
  const periodMeta = {
    today:    { days: 1,  label: '오늘',       itemLabel: '오늘 항목',       newLabel: '오늘 신규',       hint: 'today 발행 기준' },
    '7days':  { days: 7,  label: '최근 7일',   itemLabel: '최근 7일 항목',   newLabel: '최근 7일 신규',   hint: '최근 7일 발행 기준' },
    '30days': { days: 30, label: '최근 30일',  itemLabel: '최근 30일 항목',  newLabel: '최근 30일 신규',  hint: '최근 30일 발행 기준' },
    all:      { days: 60, label: '전체 누적',  itemLabel: '전체 항목',       newLabel: '전체 신규',       hint: 'source_history 60일' },
  };
  const meta = periodMeta[period] || periodMeta['7days'];

  // KST 날짜 키 생성 — renderSourcesStatus와 동일
  const kstDateStr = (d) => {
    const kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
    return kst.toISOString().slice(0, 10);
  };
  const todayKst = kstDateStr(new Date());
  const periodDayKeys = (() => {
    const ks = [];
    const today = new Date();
    for (let i = 0; i < meta.days; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      ks.push(kstDateStr(d));
    }
    return ks;
  })();
  const periodDaySet = new Set(periodDayKeys);
  const cutoffDate = periodDayKeys[periodDayKeys.length - 1];  // 가장 오래된 날짜

  // 1. 기간 내 발행 항목 (KST 발행일 기준) — 하단 표의 신규와 다른 정의(URL 1회)이지만
  //    "선택 기간에 보고 있는 항목 수"로서 의미가 있음
  const allItems = state.data.items || [];
  const periodItems = allItems.filter(it => {
    if (!it.date) return false;
    const d = new Date(it.date);
    if (isNaN(d)) return false;
    return kstDateStr(d) >= cutoffDate;
  });

  // v3.4: 기간 내 신규 수집 — items의 발행일(date) 기준 unique URL 카운트
  //   사용자 정책: 뉴스 피드 '오늘'(발행일)과 소스 현황 '오늘 신규' 정의 통일
  const history = state.sourceHistory || {};
  const periodNew = (() => {
    let cnt = 0;
    for (const it of allItems) {
      if (!it.date) continue;
      const d = new Date(it.date);
      if (isNaN(d)) continue;
      if (kstDateStr(d) >= cutoffDate && kstDateStr(d) <= todayKst) cnt += 1;
    }
    return cnt;
  })();

  // 3. AI 분석 완료 — 기간 내 항목 중 llm_enriched
  const periodEnriched = periodItems.filter(it => it.llm_enriched).length;

  // 4. 유사 뉴스 병합 — 기간 내 항목 중 related_count > 0
  const periodRelated = periodItems.filter(it => (it.related_count || 0) > 0).length;

  // 5. 활성 소스 — 기간 내에 한 번이라도 fetched > 0 이었던 소스 수
  const sources = state.data.sources || [];
  let periodActive = 0;
  for (const s of sources) {
    const h = history[s.name] || {};
    let active = false;
    for (const k of periodDayKeys) {
      if (h[k] && (h[k].fetched || 0) > 0) { active = true; break; }
    }
    // source_history에 흔적이 없어도 이번 빌드에서 active면 포함 (오늘만 선택 시 fresh 빌드)
    if (!active && period === 'today' && s.status === 'active') active = true;
    if (active) periodActive += 1;
  }

  // 6. LLM 백엔드 (그대로)
  const backend = state.data.llm_backend || 'none';
  const backendLabel = {
    'claude-cli': 'Claude CLI', 'anthropic': 'Anthropic SDK',
    'openai': 'OpenAI SDK', 'none': '비활성',
  }[backend] || backend;

  row.innerHTML = `
    <div class="stat-card accent">
      <span class="stat-label">${escapeHtml(meta.itemLabel)}</span>
      <span class="stat-value">${periodItems.length}</span>
      <span class="stat-hint">${escapeHtml(meta.hint)}</span>
    </div>
    <div class="stat-card highlight">
      <span class="stat-label">${escapeHtml(meta.newLabel)}</span>
      <span class="stat-value">${periodNew}</span>
      <span class="stat-hint">소스별 신규 URL 합산</span>
    </div>
    <div class="stat-card success">
      <span class="stat-label">AI 분석 완료</span>
      <span class="stat-value">${periodEnriched}</span>
      <span class="stat-hint">${escapeHtml(meta.label)} 항목 중</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">유사 뉴스 병합</span>
      <span class="stat-value">${periodRelated}</span>
      <span class="stat-hint">${escapeHtml(meta.label)} 항목 중</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">활성 소스</span>
      <span class="stat-value">${periodActive} / ${sources.length}</span>
      <span class="stat-hint">${escapeHtml(meta.label)} 동안 활성</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">LLM 백엔드</span>
      <span class="stat-value" style="font-size:16px;">${escapeHtml(backendLabel)}</span>
      <span class="stat-hint">이번 빌드</span>
    </div>
  `;
}

function renderCategoryBar() {
  const bar = document.getElementById('category-bar');
  const label = document.querySelector('.filter-label');
  if (state.view === 'strategy' || state.view === 'sources') {
    bar.style.display = 'none';
    if (label) label.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  if (label) label.style.display = 'block';

  // v2.7.1: 카테고리 카운트는 "현재 적용된 lang/date/search 필터"까지 반영해야
  // 표시되는 카드 수와 일치한다 (category 자체만 제외).
  const pool = applyNonCategoryFilters(applyViewFilter(state.data.items || []));
  const counts = {};
  pool.forEach(item => (item.categories || []).forEach(c => counts[c] = (counts[c] || 0) + 1));

  bar.innerHTML = CATEGORIES.map(cat => {
    const cnt = cat.id === 'all' ? pool.length : (counts[cat.id] || 0);
    // v2.8.3: 다중 선택 — Set에 포함되면 active
    const active = state.categories.has(cat.id) ? 'active' : '';
    return `<button class="cat-chip ${active}" data-category="${cat.id}"><span>${escapeHtml(cat.label)}</span><span class="cat-count">${cnt}</span></button>`;
  }).join('');

  bar.querySelectorAll('.cat-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const id = chip.dataset.category;
      // v2.8.3: OR 다중 선택 로직
      if (id === 'all') {
        // 'all' 클릭 → 다른 거 다 해제, all만 선택
        state.categories = new Set(['all']);
      } else {
        // 다른 카테고리 클릭 → 'all' 자동 해제 + toggle
        state.categories.delete('all');
        if (state.categories.has(id)) {
          state.categories.delete(id);
          if (state.categories.size === 0) {
            state.categories.add('all');  // 아무것도 없으면 all 복원
          }
        } else {
          state.categories.add(id);
        }
      }
      // legacy state.category 동기화 (UI 한줄 표시 등 호환)
      state.category = state.categories.has('all') ? 'all'
        : (state.categories.size === 1 ? Array.from(state.categories)[0] : 'multi');
      renderCategoryBar();
      renderContent();
    });
  });
}

// v6.15.27 (2026-05-29): persona_score 우선 정렬 — 사용자 정책
//   기존: score(0~120)만으로 정렬 → cap 도달 기사들 변별 못 함
//   변경: persona_score(0~10) > score(보조) > date(타이) 순.
//   LLM 가치 평가가 dominant. ps 없는 기사는 -1로 정렬 (하단으로).
function _sortByImportance(a, b) {
  const psA = a.persona_score != null ? a.persona_score : -1;
  const psB = b.persona_score != null ? b.persona_score : -1;
  if (psB !== psA) return psB - psA;  // persona 높은 순
  const scA = a.score || 0;
  const scB = b.score || 0;
  if (scB !== scA) return scB - scA;  // 동률이면 score
  return new Date(b.date) - new Date(a.date);  // 그래도 동률이면 최신
}

function applyViewFilter(items) {
  let arr = items.slice();
  // v2.7.1: latest/top/today 통합 → state.sortBy로 분기
  if (state.view === 'latest') {
    switch (state.sortBy) {
      case 'score':
        // v6.15.27: persona_score 우선 + score 보조
        arr.sort(_sortByImportance);
        break;
      case 'today': {
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        arr = arr.filter(i => new Date(i.first_seen || i.date) >= start);
        arr.sort(_sortByImportance);
        break;
      }
      case 'latest':
      default:
        arr.sort((a, b) => new Date(b.date) - new Date(a.date));
        break;
    }
  } else if (state.view === 'saved') {
    arr = arr.filter(i => isSaved('items', i.url));
    arr.sort(_sortByImportance);
  }
  // 'top'/'today' 구 view 이름은 백워드 호환을 위해 latest+sortBy로 매핑
  return arr;
}

// v6.15.8: sidebar active class를 현재 state.view에 동기화.
//   원인: HTML default가 nav-item active (시사점). init()이 state.view를 URL에서
//   복원하지만 sidebar class는 안 건드림 → deep URL 진입(/papers, /graph 등) 시
//   화면과 sidebar가 어긋남. renderContent 시작에서 매번 sync.
function syncSidebarActive() {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.nav-sub').forEach(n => n.classList.remove('active'));
  if (state.view === 'sources') {
    // sources view: parent nav-item + nav-sub 둘 다 active
    const parent = document.querySelector('.nav-item[data-view="sources"]');
    if (parent) parent.classList.add('active');
    const subTab = state.sourcesTab === 'trend' ? 'trend' : 'status';
    const sub = document.querySelector(`.nav-sub[data-tab="${subTab}"]`);
    if (sub) sub.classList.add('active');
  } else {
    const navEl = document.querySelector(`.nav-item[data-view="${state.view}"]`);
    if (navEl) navEl.classList.add('active');
  }
}

function renderContent() {
  syncSidebarActive();  // v6.15.8: view 전환 시마다 sidebar 자동 동기화
  const newsGrid = document.getElementById('news-grid');
  const stratView = document.getElementById('strategy-view');
  const sourcesView = document.getElementById('sources-view');
  const papersView = document.getElementById('papers-view');
  const entitiesView = document.getElementById('entities-view');
  const graphView = document.getElementById('graph-view');
  const controlsRow = document.querySelector('.controls-row');
  const filterLabel = document.querySelector('.filter-label');
  const statRow = document.getElementById('stat-row');
  const categoryBar = document.getElementById('category-bar');
  const title = document.getElementById('topbar-title');
  const hint = document.getElementById('view-hint');

  newsGrid.classList.add('hidden');
  stratView.classList.add('hidden');
  sourcesView.classList.add('hidden');
  if (papersView) papersView.classList.add('hidden');
  if (entitiesView) entitiesView.classList.add('hidden');
  if (graphView) graphView.classList.add('hidden');
  controlsRow.style.display = 'flex';
  if (filterLabel) filterLabel.style.display = 'block';
  // 기본 — v2.7: stat-row는 소스 현황 view에만 표시 (다른 view에서는 숨김)
  if (statRow) statRow.style.display = 'none';
  if (categoryBar) categoryBar.style.display = '';
  // 카테고리바 우측 기간 dropdown은 sources view에서만 표시
  const periodAside = document.getElementById('category-bar-aside');
  if (periodAside) periodAside.classList.add('hidden');

  const meta = VIEW_META[state.view] || VIEW_META.latest;
  title.textContent = meta.title;
  if (hint) hint.textContent = meta.hint;

  if (state.view === 'strategy') {
    stratView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderStrategy();
    return;
  }
  if (state.view === 'sources') {
    sourcesView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    // 소스 현황에서만 stat-row + 카테고리 탭 우측 기간 dropdown 표시
    if (statRow) statRow.style.display = '';
    if (periodAside) periodAside.classList.remove('hidden');
    renderCategoryBar();
    renderSourcesView();
    renderStats();
    return;
  }
  if (state.view === 'papers') {
    if (papersView) papersView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderPapersView();
    return;
  }

  // Phase 2b: 엔티티 view
  if (state.view === 'entities') {
    if (entitiesView) entitiesView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderEntitiesView();
    return;
  }

  // Phase 3: 지식그래프 view
  if (state.view === 'graph') {
    const graphView = document.getElementById('graph-view');
    if (graphView) graphView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderGraphView();
    return;
  }

  newsGrid.classList.remove('hidden');
  // v2.8.8: renderAnalysesView/renderSavedView가 설정한 inline display 잔존 제거 — grid 복원
  newsGrid.style.display = '';
  renderCategoryBar();
  renderStats();

  // v2.7: 저장한 항목 view는 시사점 + 뉴스 카드 둘 다 렌더
  if (state.view === 'saved') {
    renderSavedView(newsGrid);
    return;
  }

  // v2.7.5: AI 분석 결과 history view
  if (state.view === 'analyses') {
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderAnalysesView(newsGrid);
    return;
  }

  const filtered = filterItems();
  if (filtered.length === 0) {
    newsGrid.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">조건에 맞는 항목이 없습니다</div></div>`;
    return;
  }
  newsGrid.innerHTML = filtered.map(renderCard).join('');
  newsGrid.querySelectorAll('.related-badge').forEach(b => {
    b.addEventListener('click', e => {
      const detail = e.currentTarget.closest('.news-card').querySelector('.related-detail');
      if (detail) detail.classList.toggle('open');
    });
  });
}

function renderSavedView(root) {
  // v2.7.4: 저장 시점(savedAt) 기준 desc 정렬 — 최근 저장한 항목이 위로
  const savedItems = (state.data.items || [])
    .filter(i => isSaved('items', i.url))
    .map(i => ({ item: i, savedAt: getSavedAt('items', i.url) }))
    .sort((a, b) => b.savedAt - a.savedAt);
  const savedStrategies = Object.entries(state.saved.strategy || {})
    .sort((a, b) => {
      const ta = (a[1] && a[1].savedAt) || 0;
      const tb = (b[1] && b[1].savedAt) || 0;
      return tb - ta;
    });

  // v6.11: 빈 상태에서도 import만큼은 가능하게 (PC 변경·복구 시나리오)
  // v6.12: 다운로드 버튼도 disabled로 노출 (UX 일관성 — 사용자가 두 버튼 항상 같이 보길 기대)
  if (savedItems.length === 0 && savedStrategies.length === 0) {
    root.innerHTML = `
      <div class="saved-toolbar">
        <div class="saved-toolbar-info">총 0건 저장됨</div>
        <div class="saved-toolbar-spacer"></div>
        <button class="saved-toolbar-btn" id="bookmark-export-btn" disabled title="저장된 북마크가 없어 다운로드할 수 없습니다">
          📥 다운로드
        </button>
        <label class="saved-toolbar-btn" title="이전에 다운로드한 JSON으로 북마크 복원">
          📤 가져오기
          <input type="file" id="bookmark-import-input" accept="application/json,.json" hidden />
        </label>
      </div>
      <div class="saved-empty"><div style="font-size:32px;margin-bottom:8px;">★</div>아직 저장한 항목이 없습니다.<br><span style="font-size:13px;color:#9ca3af;">시사점 카드나 뉴스 카드의 ☆ 별표를 눌러 저장하세요.</span></div>`;
    wireBookmarkToolbar(root);
    return;
  }

  // 저장 시점 포맷터
  const fmtSavedAt = (ts) => {
    if (!ts || ts < 100) return '';
    const d = new Date(ts);
    const yy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${yy}-${mm}-${dd} ${hh}:${mi}`;
  };

  // v2.7.7: 시사점/뉴스 탭 분리 — 검색창 아래 탭 UI
  const counts = { insights: savedStrategies.length, news: savedItems.length };
  // 활성 탭 결정: state.savedTab 유지하되 비어있으면 다른 탭으로 자동 전환
  let activeTab = state.savedTab || 'insights';
  if (activeTab === 'insights' && counts.insights === 0 && counts.news > 0) activeTab = 'news';
  if (activeTab === 'news' && counts.news === 0 && counts.insights > 0) activeTab = 'insights';
  state.savedTab = activeTab;

  // v6.11: 북마크 toolbar — 다운로드(JSON export) + 가져오기(JSON import)
  let html = `
    <div class="saved-toolbar">
      <div class="saved-toolbar-info">총 ${counts.insights + counts.news}건 저장됨</div>
      <div class="saved-toolbar-spacer"></div>
      <button class="saved-toolbar-btn" id="bookmark-export-btn" title="현재 북마크를 JSON 파일로 다운로드">
        📥 다운로드
      </button>
      <label class="saved-toolbar-btn" title="이전에 다운로드한 JSON으로 북마크 복원/병합">
        📤 가져오기
        <input type="file" id="bookmark-import-input" accept="application/json,.json" hidden />
      </label>
    </div>
    <div class="saved-tabs">
      <button class="saved-tab ${activeTab === 'insights' ? 'active' : ''}" data-saved-tab="insights">
        ⭐ 시사점 <span class="saved-tab-count">${counts.insights}</span>
      </button>
      <button class="saved-tab ${activeTab === 'news' ? 'active' : ''}" data-saved-tab="news">
        📰 뉴스 <span class="saved-tab-count">${counts.news}</span>
      </button>
    </div>
  `;

  // 저장한 시사점 카드 (insights 탭일 때만) — v3.2: 시사점 페이지와 동일한 footer 구조
  if (activeTab === 'insights' && savedStrategies.length > 0) {
    // v3.2: state.trendCardMap에도 등록 (AI 분석 시 trend 본문+근거 포함 위해)
    state.trendCardMap = state.trendCardMap || {};
    html += `<div class="saved-list">`;
    html += savedStrategies.map(([k, entry]) => {
      const card = (entry && entry.card) || {};
      const period = (entry && entry.period) || '';
      const keyLabel = (entry && entry.key) || '';
      const savedAtLabel = fmtSavedAt(entry && entry.savedAt);
      state.trendCardMap[k] = { period, periodKey: keyLabel, card };
      const checked = state.selectedTrends.has(k);
      const citations = Array.isArray(card.citations) ? card.citations : [];
      const citationsBlock = citations.length > 0 ? `
        <details class="strategy-citations">
          <summary>근거 ${citations.length}건 ▾</summary>
          <ol class="citation-list">
            ${citations.map(c => `<li>${c.num ? `<span class="citation-num">(${c.num}번)</span> ` : ''}<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title)}</a><span class="citation-meta">— ${escapeHtml(c.source)} · ${escapeHtml(c.date)}</span></li>`).join('')}
          </ol>
        </details>` : '';
      return `
        <div class="strategy-card${checked ? ' is-selected' : ''}" data-trend-key="${escapeHtml(k)}">
          <div class="strategy-card-head">
            <div>
              <div class="strat-tag">${escapeHtml(card.tag || 'TREND')} · ${escapeHtml(period)} ${escapeHtml(keyLabel)}</div>
              <h3>${escapeHtml(card.title || '')}</h3>
            </div>
          </div>
          <div class="strategy-card-grid">
            <p class="strategy-body">${escapeHtmlWithMark(card.body || '')}</p>
            <div class="strategy-action">
              <span class="action-label">ACTION</span>
              <div class="action-body">${escapeHtmlWithMark(card.action || '')}</div>
            </div>
          </div>
          <div class="strategy-card-footer">
            <input type="checkbox" class="trend-check" data-trend-key="${escapeHtml(k)}" ${checked ? 'checked' : ''} title="AI 분석 대상으로 선택" />
            <button class="bookmark-btn is-saved" data-bookmark-strategy='${escapeAttr(JSON.stringify({k, period, key: keyLabel, card}))}' title="저장 해제">★</button>
            ${citationsBlock}
          </div>
          ${savedAtLabel ? `<div class="saved-at-label">저장 ${escapeHtml(savedAtLabel)}</div>` : ''}
        </div>
      `;
    }).join('');
    html += `</div>`;  // /.saved-list
  }

  // 저장한 뉴스 카드 — savedAt desc 순서 + 저장 시점 표시 (news 탭일 때만)
  if (activeTab === 'news' && savedItems.length > 0) {
    html += `<div class="news-grid saved-news-grid">${savedItems.map(({item, savedAt}) => {
      const card = renderCard(item);
      const label = fmtSavedAt(savedAt);
      // 카드 안에 저장 시점 라벨 inject (card-bottom 위)
      return label
        ? card.replace('<div class="card-bottom">', `<div class="saved-at-label">저장 ${escapeHtml(label)}</div><div class="card-bottom">`)
        : card;
    }).join('')}</div>`;
  }

  // 활성 탭이 비어있을 때 안내
  if ((activeTab === 'insights' && counts.insights === 0) || (activeTab === 'news' && counts.news === 0)) {
    html += `<div class="saved-empty"><div style="font-size:28px;margin-bottom:8px;">${activeTab === 'insights' ? '⭐' : '📰'}</div>저장된 ${activeTab === 'insights' ? '시사점' : '뉴스'}이 없습니다.</div>`;
  }

  root.innerHTML = html;

  // 탭 클릭 이벤트
  root.querySelectorAll('[data-saved-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.savedTab = btn.dataset.savedTab;
      renderSavedView(root);
    });
  });

  // v3.2: 저장한 항목 페이지의 시사점 카드 체크박스
  root.querySelectorAll('.trend-check').forEach(cb => {
    cb.addEventListener('change', e => {
      e.stopPropagation();
      const key = cb.dataset.trendKey;
      toggleTrendSelection(key);
    });
    cb.addEventListener('click', e => e.stopPropagation());
  });

  // v6.11: 북마크 toolbar (export/import) 이벤트 wiring
  wireBookmarkToolbar(root);
}

// v6.11: 북마크 toolbar 이벤트 wiring — export(JSON download) + import(JSON upload & merge)
function wireBookmarkToolbar(root) {
  // === Export ===
  const exportBtn = root.querySelector('#bookmark-export-btn');
  if (exportBtn && !exportBtn.disabled) {
    exportBtn.addEventListener('click', () => {
      try {
        // localStorage 직접 읽기 (state.saved와 일관성 보장)
        const raw = localStorage.getItem(SAVED_STORAGE_KEY);
        if (!raw) {
          alert('저장된 북마크가 없습니다.');
          return;
        }
        // KST 기준 파일명 (YYYYMMDD)
        const now = new Date();
        const yyyymmdd =
          now.getFullYear().toString() +
          String(now.getMonth() + 1).padStart(2, '0') +
          String(now.getDate()).padStart(2, '0');
        const filename = `daibfy_bookmarks_${yyyymmdd}.json`;

        // 예쁘게 indent된 JSON으로 저장 (사람이 열어 볼 수 있게)
        let pretty;
        try {
          pretty = JSON.stringify(JSON.parse(raw), null, 2);
        } catch (e) {
          pretty = raw; // parse 실패해도 raw 그대로
        }

        const blob = new Blob([pretty], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        // 다음 tick에 revoke (일부 브라우저 즉시 revoke 시 다운로드 중단)
        setTimeout(() => URL.revokeObjectURL(url), 1500);
      } catch (err) {
        console.error('bookmark export failed', err);
        alert('다운로드 실패: ' + (err.message || err));
      }
    });
  }

  // === Import (merge, 덮어쓰기 X) ===
  const importInput = root.querySelector('#bookmark-import-input');
  if (importInput) {
    importInput.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const text = String(ev.target.result || '');
          const parsed = JSON.parse(text);
          if (!parsed || typeof parsed !== 'object') {
            throw new Error('JSON 구조가 올바르지 않습니다.');
          }
          const newItems = (parsed.items && typeof parsed.items === 'object') ? parsed.items : {};
          const newStrategy = (parsed.strategy && typeof parsed.strategy === 'object') ? parsed.strategy : {};
          const inCount = Object.keys(newItems).length + Object.keys(newStrategy).length;
          if (inCount === 0) {
            throw new Error('파일에 북마크 항목이 없습니다.');
          }

          // 현재 상태 로드 (단일 source = localStorage)
          let current = { items: {}, strategy: {} };
          try {
            const raw = localStorage.getItem(SAVED_STORAGE_KEY);
            if (raw) {
              const cp = JSON.parse(raw);
              current.items = cp.items || {};
              current.strategy = cp.strategy || {};
            }
          } catch (_) {}

          const beforeN = Object.keys(current.items).length + Object.keys(current.strategy).length;

          // Merge 정책: savedAt 더 최신인 쪽이 이김 (or 신규 항목은 그대로 추가)
          for (const [k, v] of Object.entries(newItems)) {
            const cur = current.items[k];
            if (!cur || ((v && v.savedAt) || 0) > ((cur && cur.savedAt) || 0)) {
              current.items[k] = v;
            }
          }
          for (const [k, v] of Object.entries(newStrategy)) {
            const cur = current.strategy[k];
            if (!cur || ((v && v.savedAt) || 0) > ((cur && cur.savedAt) || 0)) {
              current.strategy[k] = v;
            }
          }

          const merged = { items: current.items, strategy: current.strategy };
          const afterN = Object.keys(merged.items).length + Object.keys(merged.strategy).length;
          const added = afterN - beforeN;

          // 확인 후 적용
          const proceed = confirm(
            `JSON 파일에서 북마크 ${inCount}건을 발견했습니다.\n\n` +
            `· 현재: ${beforeN}건\n` +
            `· 병합 후: ${afterN}건 (신규 +${added})\n\n` +
            `덮어쓰지 않고 병합합니다. 진행할까요?`
          );
          if (!proceed) {
            importInput.value = '';
            return;
          }

          // 저장 → state 동기화
          localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(merged));
          state.saved = merged;

          alert(`✅ 북마크 ${added}건이 새로 추가되었습니다 (총 ${afterN}건).`);
          // 페이지 재렌더
          renderSavedView(root);
        } catch (err) {
          console.error('bookmark import failed', err);
          alert('가져오기 실패: ' + (err.message || err) + '\n\n파일이 daibfy 북마크 JSON 형식인지 확인해주세요.');
        } finally {
          // input 초기화 (같은 파일 재선택 가능하게)
          importInput.value = '';
        }
      };
      reader.onerror = () => {
        alert('파일을 읽지 못했습니다.');
      };
      reader.readAsText(file, 'utf-8');
    });
  }
}

// v2.7.5: AI 분석 결과 history view
function renderAnalysesView(root) {
  const list = state.analyses || [];
  root.style.display = 'block';
  if (list.length === 0) {
    root.innerHTML = `<div class="saved-empty"><div style="font-size:32px;margin-bottom:8px;">🤖</div>아직 저장된 AI 분석 결과가 없습니다.<br><span style="font-size:13px;color:#9ca3af;">뉴스 카드를 여러 개 선택하고 "🤖 AI 분석" 버튼을 누르면 결과가 자동으로 여기 저장됩니다.</span></div>`;
    return;
  }
  const fmt = (ts) => {
    const d = new Date(ts);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  };
  const promptPreset = (id) => {
    const map = {
      summary: '핵심 요약', insights: '시사점',
      trends: '트렌드 분석', competitive: '경쟁 구도',
      opportunity: '한국 시장 진출 기회', custom: '직접 입력',
    };
    return map[id] || id || '';
  };
  root.innerHTML = `
    <div class="analyses-list">
      ${list.map(a => `
        <div class="analysis-entry" data-analysis-id="${escapeHtml(a.id)}">
          <div class="analysis-head">
            <div>
              <div class="analysis-time">${escapeHtml(fmt(a.timestamp))}</div>
              <div class="analysis-meta-row">
                <span class="analysis-backend">${escapeHtml(a.backend || '?')}</span>
                <span class="analysis-model">${escapeHtml(a.model || '?')}</span>
                <span class="analysis-count">${(a.items || []).length}개 항목</span>
                ${a.promptPreset ? `<span class="analysis-preset">${escapeHtml(promptPreset(a.promptPreset))}</span>` : ''}
              </div>
            </div>
            <div class="analysis-actions">
              <button class="link-btn" data-toggle-analysis="${escapeHtml(a.id)}">결과 보기 ▾</button>
              <button class="link-btn analysis-del" data-delete-analysis="${escapeHtml(a.id)}" title="삭제">×</button>
            </div>
          </div>
          <details class="analysis-detail">
            <summary>분석 대상 ${(a.items || []).length}건 ▾</summary>
            <ol class="analysis-items">
              ${(a.items || []).map(it => `<li><a href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a> <span class="rel-source">— ${escapeHtml(it.source || '')} · ${escapeHtml((it.date || '').slice(0, 10))}</span></li>`).join('')}
            </ol>
          </details>
          ${a.promptText ? `<details class="analysis-prompt-detail"><summary>요청 프롬프트 ▾</summary><pre>${escapeHtml(a.promptText)}</pre></details>` : ''}
          <div class="analysis-result-body" id="analysis-result-${escapeHtml(a.id)}">${renderMarkdown(a.result || '')}</div>
        </div>
      `).join('')}
    </div>
  `;
  // 결과 보기 토글
  root.querySelectorAll('[data-toggle-analysis]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.toggleAnalysis;
      const body = root.querySelector(`#analysis-result-${id}`);
      if (body) body.classList.toggle('hidden');
      btn.textContent = body.classList.contains('hidden') ? '결과 보기 ▾' : '접기 ▴';
    });
  });
  // 삭제
  root.querySelectorAll('[data-delete-analysis]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.deleteAnalysis;
      if (confirm('이 분석 결과를 삭제할까요?')) {
        deleteAnalysis(id);
        renderContent();
      }
    });
  });
}

// v2.7.1: 카테고리 외 필터만 적용 (chip 카운트 계산용)
function applyNonCategoryFilters(items) {
  let arr = items;
  if (state.langFilter !== 'all') {
    arr = arr.filter(i => i.lang === state.langFilter);
  }
  if (state.dateFilter === 'specific') {
    // v6.15.26 (2026-05-29): 특정 일자 필터 — 사용자 정책
    //   specificDate가 비어있으면 필터 작동 X (사용자 정책: '특정 일자' 선택 시 일자도 선택해야 작동)
    if (state.specificDate) {
      // YYYY-MM-DD 형식. KST 기준 해당 일자 0~24시 범위 매칭.
      arr = arr.filter(i => {
        if (!i.date) return false;
        const itemDate = new Date(i.date);
        // KST(+9) 변환 후 YYYY-MM-DD 추출
        const kstDate = new Date(itemDate.getTime() + 9 * 60 * 60 * 1000);
        const itemDateStr = kstDate.toISOString().slice(0, 10);
        return itemDateStr === state.specificDate;
      });
    }
    // specificDate 미선택 시 필터 미적용 (전체 표시) — 사용자가 일자 선택해야 작동
  } else if (state.dateFilter !== 'all') {
    const cutoff = computeDateCutoff(state.dateFilter);
    arr = arr.filter(i => new Date(i.date) >= cutoff);
  }
  if (state.search) {
    // v3.3: 동의어 OR 매칭 (영한 자동 확장)
    arr = arr.filter(i => {
      const blob = [i.title, i.summary, i.summary_ko, i.insight_ko, i.source, ...(i.categories || [])].filter(Boolean).join(' ');
      return matchSearchQuery(blob, state.search);
    });
  }
  return arr;
}

function filterItems() {
  let items = applyNonCategoryFilters(applyViewFilter(state.data.items || []));
  // v2.8.3: OR 다중 카테고리 필터
  if (!state.categories.has('all') && state.categories.size > 0) {
    items = items.filter(i => {
      const itemCats = i.categories || [];
      // 선택된 카테고리 중 하나라도 매칭되면 통과 (OR)
      for (const c of state.categories) {
        if (itemCats.includes(c)) return true;
      }
      return false;
    });
  }
  return items;
}

function computeDateCutoff(key) {
  const now = new Date();
  const d = new Date(now);
  switch (key) {
    case 'today': d.setHours(0, 0, 0, 0); break;
    case '3days': d.setDate(d.getDate() - 3); break;
    case 'week': d.setDate(d.getDate() - 7); break;
    case 'month': d.setMonth(d.getMonth() - 1); break;
  }
  return d;
}

function renderCard(item) {
  const score = item.score || 0;
  const scoreClass = score >= 80 ? 'high' : score >= 65 ? 'mid' : 'low';
  const scoreLabel = score > 0 ? `중요도 ${score}` : '신규';
  const dateStr = formatKoreanDate(new Date(item.date));
  const sourceInitial = (item.source || '?').charAt(0).toUpperCase();

  const cats = (item.categories || []).slice(0, 2).map(c => {
    const label = (CATEGORIES.find(x => x.id === c) || { label: c }).label;
    return `<span class="card-category cat-${escapeHtml(c)}">${escapeHtml(label)}</span>`;
  }).join('');

  const isEnglish = item.lang === 'en';
  const summaryKo = item.summary_ko;
  const summaryEn = item.summary;
  let summaryHtml = '';
  if (summaryKo) {
    summaryHtml = `<div class="card-summary has-ko">${escapeHtmlWithMark(summaryKo)}</div>`;
    if (isEnglish && summaryEn) {
      summaryHtml += `<details class="card-original"><summary>원문 요약 보기</summary><div class="card-original-text">${escapeHtml(summaryEn)}</div></details>`;
    }
  } else if (summaryEn) {
    summaryHtml = `<div class="card-summary ${isEnglish ? 'is-en' : ''}">${escapeHtmlWithMark(summaryEn)}</div>`;
  }

  const insightBlock = item.insight_ko ? `<div class="card-insight"><span class="insight-label">시사점</span>${escapeHtmlWithMark(item.insight_ko)}</div>` : '';

  const relCount = item.related_count || 0;
  const relBadge = relCount > 0 ? `<span class="related-badge" title="유사 뉴스 ${relCount}건">+${relCount} 매체 ▾</span>` : '';
  const relDetail = relCount > 0 && item.related ? `<div class="related-detail">${item.related.map(r => `<div class="rel-item"><span class="rel-source">${escapeHtml(r.source)}</span><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a></div>`).join('')}</div>` : '';

  // v2.7.3: ai-badge 제거 (모든 카드에 시사점이 들어가므로 의미 없음)
  const langBadge = isEnglish ? '<span class="lang-badge">EN</span>' : '';
  const newBadge = isNewToday(item) ? '<span class="new-badge">NEW</span>' : '';

  const isSelected = state.selectedUrls.has(item.url);
  const itemSaved = isSaved('items', item.url);

  return `
    <article class="news-card ${isSelected ? 'is-selected' : ''}" data-url="${escapeHtml(item.url)}">
      <div class="card-top">
        <div class="card-top-left">
          <label class="card-checkbox" title="AI 분석 선택">
            <input type="checkbox" class="card-check" data-url="${escapeHtml(item.url)}" ${isSelected ? 'checked' : ''} />
          </label>
          <span class="score-badge ${scoreClass}">${escapeHtml(scoreLabel)}</span>
          ${newBadge}
        </div>
        <div class="card-top-right">${langBadge}${relBadge}<span class="date-text">${escapeHtml(dateStr)}</span></div>
      </div>
      <div class="card-cats">${cats}</div>
      <h3 class="card-title"><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h3>
      ${summaryHtml}
      ${insightBlock}
      ${relDetail}
      <div class="card-bottom">
        <button class="bookmark-btn card-bookmark ${itemSaved ? 'is-saved' : ''}" data-bookmark-item="${escapeHtml(item.url)}" title="${itemSaved ? '저장 해제' : '저장하기'}">${itemSaved ? '★' : '☆'}</button>
        <span class="card-source"><span class="card-source-icon">${escapeHtml(sourceInitial)}</span>${escapeHtml(item.source || '')}</span>
        <div class="card-actions">
          <button class="icon-btn card-share" data-share-url="${escapeHtml(item.url)}" title="원문 URL 복사" type="button">⎘</button>
          <a class="icon-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" title="원문">↗</a>
        </div>
      </div>
    </article>
  `;
}

// ========================= 시사점 (시계열) =========================

function getStrategyKeys(period) {
  if (!state.history || !state.history[period]) return [];
  return Object.keys(state.history[period]).sort().reverse();
}

function getCurrentStrategyKey(period) {
  // state.strategyKey가 명시되어 있고 해당 period에 있으면 사용
  const keys = getStrategyKeys(period);
  if (state.strategyKey && keys.includes(state.strategyKey)) {
    return state.strategyKey;
  }
  return keys[0] || null;
}

function renderStrategy() {
  // period 셀렉트
  const select = document.getElementById('strategy-period-select');
  const period = state.strategyPeriod;

  // 탭 active 표시
  document.querySelectorAll('.period-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.period === period);
  });

  const keys = getStrategyKeys(period);

  if (period === 'daily') {
    // Daily는 보통 최신만 보여주지만, 셀렉트로 과거 일자 선택 가능
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  } else if (period === 'weekly') {
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  } else if (period === 'monthly') {
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  }

  const currentKey = getCurrentStrategyKey(period);
  if (currentKey) select.value = currentKey;

  // 카드 렌더
  const root = document.getElementById('strategy-cards');
  let cards = [];
  let summaryText = '';
  let summaryAddons = [];
  if (currentKey && state.history && state.history[period]) {
    // v6.15: entry가 dict({summary, cards, _summary_addons}) 또는 list(옛 포맷) 모두 지원
    const entry = state.history[period][currentKey];
    if (Array.isArray(entry)) {
      cards = entry;
    } else if (entry && typeof entry === 'object') {
      cards = Array.isArray(entry.cards) ? entry.cards : [];
      summaryText = entry.summary || '';
      if (Array.isArray(entry._summary_addons)) summaryAddons = entry._summary_addons;
    }
  }
  // history에 아무것도 없으면 news.json의 strategy로 fallback (daily)
  if (cards.length === 0 && period === 'daily') {
    cards = state.data.strategy || [];
    summaryText = summaryText || state.data.strategy_summary || '';
  }

  // v6.15-D: 기간 박스 바로 밑의 종합 요약 영역 렌더
  // v6.15.6: label은 본문에 inline 흡수, 단락 흐름으로 가로 줄바꿈 자연스럽게.
  // v6.15.9: backend summary가 비어있을 때 cards tag로 자동 fallback (LLM 응답이
  //          dict 대신 list로 와서 summary 누락된 케이스 즉시 회복).
  const summaryRoot = document.getElementById('strategy-summary-inline');
  if (summaryRoot) {
    // fallback: summary 비어있지만 cards 있으면 tag 합성 요약 생성
    let effectiveSummary = summaryText;
    let isFallback = false;
    if (!effectiveSummary && cards.length > 0) {
      const tags = cards.slice(0, 5)
        .map(c => (c.tag || '').replace(/^TREND\s*\d+\s*[·\-]\s*/i, '').trim())
        .filter(Boolean);
      if (tags.length > 0) {
        const periodLabel = period === 'daily' ? '오늘' : period === 'weekly' ? '이번 주' : '이번 달';
        effectiveSummary = `${periodLabel} ${cards.length}개 trend가 부상. 주요 흐름은 <strong>${tags.map(t => escapeHtml(t)).join(' / ')}</strong>이다. (자동 요약 — 다음 빌드에서 LLM 종합으로 대체)`;
        isFallback = true;
      }
    }

    if (effectiveSummary || summaryAddons.length > 0) {
      const addonHtml = summaryAddons.length > 0
        ? `<div class="strategy-summary-addons">${summaryAddons.map(a => `<span class="strategy-summary-addon">+ ${escapeHtml(a)}</span>`).join('')}</div>`
        : '';
      // fallback인 경우 escapeHtml 거치지 않고 그대로 (이미 <strong> 포함된 합성 HTML)
      const renderedSummary = isFallback
        ? effectiveSummary  // 이미 안전한 HTML (cards tag는 위에서 escapeHtml됨)
        : escapeHtmlWithMark(effectiveSummary);
      const mainHtml = effectiveSummary
        ? `<p class="strategy-summary-main${isFallback ? ' strategy-summary-fallback' : ''}"><strong class="strategy-summary-label">📌 종합</strong> ${renderedSummary}</p>`
        : '';
      summaryRoot.innerHTML = mainHtml + addonHtml;
      summaryRoot.classList.remove('hidden');
    } else {
      summaryRoot.innerHTML = '';
      summaryRoot.classList.add('hidden');
    }
  }

  if (cards.length === 0) {
    root.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-title">${escapeHtml(period === 'weekly' ? '아직 주간 시사점이 없습니다' : period === 'monthly' ? '아직 월간 시사점이 없습니다' : '시사점이 없습니다')}</div>
        <div class="empty-desc">매일 빌드가 누적되면서 점차 채워집니다.</div>
      </div>
    `;
    return;
  }

  // v3.0: trend 데이터를 cardKey로 조회 가능하게 caching — AI 분석에서 사용
  state.trendCardMap = state.trendCardMap || {};

  root.innerHTML = cards.map(s => {
    const citations = Array.isArray(s.citations) ? s.citations : [];
    const citationsBlock = citations.length > 0 ? `
      <details class="strategy-citations">
        <summary>근거 ${citations.length}건 ▾</summary>
        <ol class="citation-list">
          ${citations.map(c => `<li><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title)}</a><span class="citation-meta">— ${escapeHtml(c.source)} · ${escapeHtml(c.date)}</span></li>`).join('')}
        </ol>
      </details>` : '';
    const cardKey = makeStrategyKey(period, currentKey, s);
    const saved = isSaved('strategy', cardKey);
    // v3.0: cardKey → 카드 데이터 매핑 (체크박스로 선택 시 AI 분석 input 구성용)
    state.trendCardMap[cardKey] = { period, periodKey: currentKey, card: s };
    const checked = state.selectedTrends.has(cardKey);
    // v3.2: 좌측 하단 footer — 체크박스 → 즐겨찾기 → 근거 순서
    return `
      <div class="strategy-card${checked ? ' is-selected' : ''}" data-trend-key="${escapeHtml(cardKey)}">
        <div class="strategy-card-head">
          <div>
            <div class="strat-tag">${escapeHtml(s.tag || 'TREND')}</div>
            <h3>${escapeHtml(s.title || '')}</h3>
          </div>
        </div>
        <div class="strategy-card-grid">
          <p class="strategy-body">${escapeHtmlWithMark(s.body || '')}</p>
          <div class="strategy-action">
            <span class="action-label">ACTION</span>
            <div class="action-body">${escapeHtmlWithMark(s.action || '')}</div>
          </div>
        </div>
        <div class="strategy-card-footer">
          <input type="checkbox" class="trend-check" data-trend-key="${escapeHtml(cardKey)}" ${checked ? 'checked' : ''} title="AI 분석 대상으로 선택" />
          <button class="bookmark-btn ${saved ? 'is-saved' : ''}" data-bookmark-strategy='${escapeAttr(JSON.stringify({k: cardKey, period, key: currentKey, card: s}))}' title="${saved ? '저장 해제' : '저장하기'}">${saved ? '★' : '☆'}</button>
          ${citationsBlock}
        </div>
      </div>
    `;
  }).join('');

  // v3.0: trend 체크박스 이벤트
  root.querySelectorAll('.trend-check').forEach(cb => {
    cb.addEventListener('change', e => {
      e.stopPropagation();
      const key = cb.dataset.trendKey;
      toggleTrendSelection(key);
    });
    cb.addEventListener('click', e => e.stopPropagation());
  });
}

// ========================= 소스 현황 (status / trend) =========================

function renderSourcesView() {
  const statusTab = document.getElementById('sources-tab-status');
  const trendTab = document.getElementById('sources-tab-trend');

  // 사이드바 nav-sub active 상태 반영 (이미 bindEvents에서 처리)

  if (state.sourcesTab === 'trend') {
    statusTab.classList.add('hidden');
    trendTab.classList.remove('hidden');
    renderSourceTrend();
  } else {
    statusTab.classList.remove('hidden');
    trendTab.classList.add('hidden');
    renderSourcesStatus();
  }
}

function renderSourcesStatus() {
  const root = document.getElementById('sources-table');
  const sources = state.data.sources || [];
  if (sources.length === 0) {
    root.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div class="empty-title">소스 정보 없음</div></div>';
    return;
  }

  // v2.8.1: KST 기준 날짜 키 생성 — source_history.py가 KST로 기록하므로 매칭
  // 이전 버그: d.toISOString().slice(0,10)는 UTC 날짜 → KST 06:00 이전엔 mismatch
  const kstDateStr = (d) => {
    const kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
    return kst.toISOString().slice(0, 10);
  };
  const today = new Date();
  const periodDayKeys = (() => {
    const ks = [];
    const make = n => {
      for (let i = 0; i < n; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        ks.push(kstDateStr(d));
      }
    };
    if (state.sourcesPeriod === 'today') make(1);
    else if (state.sourcesPeriod === '7days') make(7);
    else if (state.sourcesPeriod === '30days') make(30);
    else make(60); // all — source_history는 60일 보존
    return ks;
  })();

  const history = state.sourceHistory || {};

  // source_type 결정 — items에서 추정 (items의 source가 일치하는 첫 항목의 source_type)
  const itemBySource = {};
  for (const it of (state.data.items || [])) {
    if (it.source && !itemBySource[it.source]) itemBySource[it.source] = it;
  }

  // v3.6: items 기반 소스별 카운트 — 발행일이 기간 내인 unique URL을 첫 수집 소스(item.source)에 1회 카운트
  //   각 URL은 한 소스에만 속하므로 표 합산 = 헤더 unique URL 수와 정확히 일치
  const itemsBySourceMap = {};
  for (const it of (state.data.items || [])) {
    if (!it.date || !it.source) continue;
    const d = new Date(it.date);
    if (isNaN(d)) continue;
    const k = kstDateStr(d);
    if (!periodDayKeys.includes(k)) continue;
    if (!itemsBySourceMap[it.source]) itemsBySourceMap[it.source] = 0;
    itemsBySourceMap[it.source] += 1;
  }

  // 소스별로 row 계산
  const enriched = sources.map(s => {
    const hist = history[s.name] || {};
    // 마지막 활성일은 전체 기간으로 따로 한 번 더 봄 (선택 기간이 짧을 때 의미 없을까봐)
    let everLastActive = null;
    let periodFetched = 0;
    let lastActiveDate = null;
    for (const k of periodDayKeys) {
      const entry = hist[k];
      if (entry) {
        const f = entry.fetched || 0;
        periodFetched += f;
        if (f > 0 && (!lastActiveDate || k > lastActiveDate)) lastActiveDate = k;
      }
    }
    for (const k of Object.keys(hist)) {
      if ((hist[k]?.fetched || 0) > 0 && (!everLastActive || k > everLastActive)) everLastActive = k;
    }
    const stype = itemBySource[s.name]?.source_type || '-';
    // v3.6: periodNew는 items 기반 unique URL 카운트
    const periodNew = itemsBySourceMap[s.name] || 0;
    return {
      ...s,
      source_type: stype,
      periodFetched,
      periodNew,
      lastActive: lastActiveDate || everLastActive || '-',
    };
  });

  // v2.8.7: 정렬·합계 기준을 'new'(unique URL 신규)로 통일 — 상단 stat과 매칭
  enriched.sort((a, b) => b.periodNew - a.periodNew);

  const byStatus = enriched.reduce((a, s) => { a[s.status] = (a[s.status] || 0) + 1; return a; }, {});
  // v3.2: 표 합계 = 소스별 누적 (소스 분포 보여주는 용도, 같은 URL이 N개 소스에서 잡히면 N회 카운트)
  const periodTotalBySource = enriched.reduce((sum, s) => sum + s.periodNew, 0);
  // v3.4: 상단 카드와 동일 기준 (items의 발행일 기반 unique URL 카운트)
  const periodTotalUnique = (() => {
    const allItems = state.data.items || [];
    let cnt = 0;
    for (const it of allItems) {
      if (!it.date) continue;
      const d = new Date(it.date);
      if (isNaN(d)) continue;
      const k = kstDateStr(d);
      if (periodDayKeys.includes(k)) cnt += 1;
    }
    return cnt;
  })();

  const statusBadge = (st) => {
    const label = st === 'active' ? 'Active' : st === 'error' ? 'Error' : 'Idle';
    return `<span class="badge-${escapeHtml(st)}">${label}</span>`;
  };
  const typeBadge = (t) => {
    const labels = { rss: 'RSS', arxiv: 'arXiv', naver: 'Naver', google_news: 'Google News', semantic_scholar: 'S2', korean: 'KR', blog: 'Blog' };
    return `<span class="type-badge type-${escapeHtml(t)}">${escapeHtml(labels[t] || t || '-')}</span>`;
  };

  const periodLabel = { today: '오늘', '7days': '최근 7일', '30days': '최근 30일', all: '전체 누적' }[state.sourcesPeriod] || '';

  // v2.8.7: '오늘 수집' + '신규' 두 컬럼 → 'new' 기준 단일 컬럼으로 통합
  const rows = enriched.map(s => `
    <tr>
      <td class="src-name">${escapeHtml(s.name)}</td>
      <td>${typeBadge(s.source_type)}</td>
      <td>${statusBadge(s.status)}</td>
      <td class="num-cell">${s.periodNew}</td>
      <td>${escapeHtml(s.lastActive)}</td>
      <td class="src-url">${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.url)}</a>` : '-'}</td>
    </tr>
  `).join('');

  root.innerHTML = `
    <div class="sources-table-wrap">
      <h3>소스 현황 — ${escapeHtml(periodLabel)} (총 ${enriched.length}개 · 활성 ${byStatus.active || 0}개 · 신규 수집 ${periodTotalUnique}건)</h3>
      <p class="sources-table-note">※ "신규" = 발행일 기간 내 unique URL을 첫 수집 소스에 1회 카운트. 표 합산 = 헤더 신규 수집 수와 일치 (${periodTotalUnique}건).</p>
      <div class="sources-table-scroll">
        <table class="src-table">
          <thead>
            <tr>
              <th class="col-name">소스</th>
              <th class="col-type">유형</th>
              <th class="col-status">상태</th>
              <th class="col-num">${escapeHtml(periodLabel)} 신규</th>
              <th class="col-date">마지막 활성</th>
              <th class="col-url">URL</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderSourceTrend() {
  // v2.8.1: KST 기준 날짜 키 (source_history.json과 일관)
  const kstDateStr = (d) => {
    const kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
    return kst.toISOString().slice(0, 10);
  };
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(kstDateStr(d));
  }

  const colors = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#0ea5e9', '#a16207'];

  // 차트 제목 + view 모드별 데이터셋
  const titleEl = document.getElementById('trend-chart-title');
  let datasets = [];
  let noteHtml = '';

  if (state.trendView === 'category') {
    if (titleEl) titleEl.textContent = '최근 7일 컨텐츠 태그별 수집 추이';
    // items의 categories 별로 발행일 기준 일별 카운트
    const items = state.data.items || [];
    const catDayMap = {}; // category → { date → count }
    for (const it of items) {
      if (it.date_unknown) continue;
      // v2.8.1: item.date를 KST 날짜로 변환 (days 배열과 일관)
      const dt = new Date(it.date);
      if (isNaN(dt)) continue;
      const d = kstDateStr(dt);
      if (!days.includes(d)) continue;
      const cats = it.categories || [];
      for (const c of cats) {
        if (!catDayMap[c]) catDayMap[c] = {};
        catDayMap[c][d] = (catDayMap[c][d] || 0) + 1;
      }
    }
    // 합계 큰 카테고리 상위 10
    const catTotals = Object.entries(catDayMap).map(([c, m]) =>
      [c, Object.values(m).reduce((a, b) => a + b, 0)]
    ).sort((a, b) => b[1] - a[1]).slice(0, 10);

    // v2.8.1: 카테고리 ID → 한글 label 매핑
    const catLabel = (id) => {
      const found = CATEGORIES.find(c => c.id === id);
      return found ? found.label : id;
    };
    datasets = catTotals.map(([cat, _], idx) => ({
      label: catLabel(cat),
      data: days.map(d => (catDayMap[cat][d] || 0)),
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length] + '20',
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 3,
    }));
    noteHtml = `<div class="trend-note">발행일 기준. 상위 ${catTotals.length}개 태그만 표시.</div>`;
  } else {
    if (titleEl) titleEl.textContent = '최근 7일 소스별 수집 추이';
    const history = state.sourceHistory || {};
    const sources = state.data.sources || [];
    const topSources = sources
      .filter(s => s.status === 'active')
      .sort((a, b) => (b.count || 0) - (a.count || 0))
      .slice(0, 8)
      .map(s => s.name);

    datasets = topSources.map((name, idx) => ({
      label: name,
      data: days.map(d => ((history[name] || {})[d]?.fetched || 0)),
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length] + '20',
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 3,
    }));
    noteHtml = `<div class="trend-note">수집일 기준. 활성 소스 중 수집량 상위 8개만 표시.</div>`;
  }

  const wrap = document.querySelector('.chart-canvas-wrap');
  if (state.trendChart) {
    state.trendChart.destroy();
    state.trendChart = null;
  }
  if (typeof Chart === 'undefined') {
    if (wrap) wrap.innerHTML = '<div class="empty-state">Chart.js 로드 실패</div>';
    return;
  }
  if (datasets.length === 0) {
    if (wrap) wrap.innerHTML = '<div class="empty-state">아직 데이터가 충분히 누적되지 않았습니다.</div>';
    return;
  }

  // canvas 복원 (이전 empty-state 메시지가 들어있을 수 있어서)
  if (wrap && !document.getElementById('trend-chart')) {
    wrap.innerHTML = '<canvas id="trend-chart"></canvas>';
  }

  const ctx = document.getElementById('trend-chart');
  state.trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: days.map(d => d.slice(5)),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 } } },
        tooltip: { mode: 'index' },
      },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 5 } } },
    },
  });

  const legend = document.getElementById('trend-legend');
  if (legend) legend.innerHTML = noteHtml;
}

// ========================= 이벤트 =========================

function bindEvents() {
  // v6.12: 뉴스 카드 공유 버튼 — 원문 URL 클립보드 복사 (event delegation)
  document.addEventListener('click', (e) => {
    const shareBtn = e.target.closest('[data-share-url]');
    if (shareBtn) {
      e.preventDefault();
      e.stopPropagation();
      const url = shareBtn.dataset.shareUrl;
      const showFeedback = (msg, isError = false) => {
        // 토스트 대신 버튼 라벨을 잠깐 바꾸기 (가벼운 피드백)
        const orig = shareBtn.textContent;
        const origTitle = shareBtn.title;
        shareBtn.textContent = isError ? '✕' : '✓';
        shareBtn.title = msg;
        shareBtn.classList.add(isError ? 'is-share-error' : 'is-share-ok');
        setTimeout(() => {
          shareBtn.textContent = orig;
          shareBtn.title = origTitle;
          shareBtn.classList.remove('is-share-ok', 'is-share-error');
        }, 1500);
      };
      // navigator.clipboard 우선, 실패 시 fallback (구형 브라우저 또는 HTTP 환경)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url)
          .then(() => showFeedback('복사됨'))
          .catch(() => {
            // 폴백 시도
            try {
              const ta = document.createElement('textarea');
              ta.value = url;
              ta.style.position = 'fixed';
              ta.style.opacity = '0';
              document.body.appendChild(ta);
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
              showFeedback('복사됨');
            } catch (err) {
              showFeedback('복사 실패', true);
            }
          });
      } else {
        try {
          const ta = document.createElement('textarea');
          ta.value = url;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          showFeedback('복사됨');
        } catch (err) {
          showFeedback('복사 실패', true);
        }
      }
      return;
    }
  });

  // v2.7: 북마크 버튼 (event delegation — 카드 동적 생성이므로)
  document.addEventListener('click', (e) => {
    const itemBtn = e.target.closest('[data-bookmark-item]');
    if (itemBtn) {
      e.preventDefault();
      e.stopPropagation();
      const url = itemBtn.dataset.bookmarkItem;
      toggleSaved('items', url, true);
      // 버튼 상태 토글
      const nowSaved = isSaved('items', url);
      itemBtn.classList.toggle('is-saved', nowSaved);
      itemBtn.textContent = nowSaved ? '★' : '☆';
      itemBtn.title = nowSaved ? '저장 해제' : '저장하기';
      // saved view면 다시 렌더해서 제거 반영
      if (state.view === 'saved') renderContent();
      return;
    }
    const stratBtn = e.target.closest('[data-bookmark-strategy]');
    if (stratBtn) {
      e.preventDefault();
      e.stopPropagation();
      try {
        const payload = JSON.parse(stratBtn.dataset.bookmarkStrategy);
        const { k, card, period, key } = payload;
        toggleSaved('strategy', k, { card, period, key });
        const nowSaved = isSaved('strategy', k);
        stratBtn.classList.toggle('is-saved', nowSaved);
        stratBtn.textContent = nowSaved ? '★' : '☆';
        stratBtn.title = nowSaved ? '저장 해제' : '저장하기';
        if (state.view === 'saved') renderContent();
      } catch (err) { console.error('bookmark parse', err); }
      return;
    }
  });

  // 사이드바 nav (parent + sub 통합)
  document.querySelectorAll('.nav-item, .nav-sub').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const view = item.dataset.view;
      if (!view) return;

      // active 표시
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.nav-sub').forEach(n => n.classList.remove('active'));
      // parent: 자신 + 첫 sub를 active로
      // sub: parent도 active로
      const parentItem = item.closest('.nav-group')?.querySelector('.nav-parent');
      if (parentItem) parentItem.classList.add('active');
      item.classList.add('active');

      // v2.7.1: 'top'/'today' 구 메뉴는 'latest' + sortBy로 매핑
      if (view === 'top') {
        state.view = 'latest';
        state.sortBy = 'score';
      } else if (view === 'today') {
        state.view = 'latest';
        state.sortBy = 'today';
      } else {
        state.view = view;
      }
      state.category = 'all';
      state.categories = new Set(['all']);  // v2.8.3: 다중 선택 초기화

      // 정렬 dropdown sync
      const sortSel = document.getElementById('sort-filter');
      if (sortSel) sortSel.value = state.sortBy;

      if (view === 'strategy') {
        const period = item.dataset.period;
        if (period) state.strategyPeriod = period;
        state.strategyKey = null;  // 항상 최신 키부터
      }
      if (view === 'sources') {
        const tab = item.dataset.tab;
        if (tab) state.sourcesTab = tab;
      }

      syncUrl();  // v6.5: URL 갱신
      renderContent();
    });
  });

  // 시사점 period 탭 (data-period 만)
  document.querySelectorAll('.period-tab[data-period]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.strategyPeriod = btn.dataset.period;
      state.strategyKey = null;
      syncUrl();  // v6.5
      renderStrategy();
    });
  });

  // 시사점 period 셀렉트 (날짜·주·월 선택)
  const select = document.getElementById('strategy-period-select');
  if (select) {
    select.addEventListener('change', e => {
      state.strategyKey = e.target.value;
      syncUrl();  // v6.5
      renderStrategy();
    });
  }

  // v2.7.1: 논문 흐름 period 탭
  document.querySelectorAll('.period-tab[data-papers-period]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.papersPeriod = btn.dataset.papersPeriod;
      state.papersKey = null;
      syncUrl();  // v6.5
      renderPapersView();
    });
  });
  const papersSel = document.getElementById('papers-period-select');
  if (papersSel) {
    papersSel.addEventListener('change', e => {
      state.papersKey = e.target.value;
      syncUrl();  // v6.5
      renderPapersView();
    });
  }

  // 일반 필터
  document.getElementById('search-input').addEventListener('input', e => {
    state.search = e.target.value.trim();
    renderContent();
    updateSelectBar();
  });
  document.getElementById('date-filter').addEventListener('change', e => {
    state.dateFilter = e.target.value;
    // v6.15.26: 특정 일자 외 옵션 선택 시 specificDate 초기화 (input은 그대로 두지만 필터 적용 X)
    if (state.dateFilter !== 'specific') {
      // specificDate 값 자체는 사용자가 다시 선택할 수 있게 보존
    }
    renderContent();
  });
  // v6.15.26 (2026-05-29): 특정 일자 input — 양방향 동기화
  const specificDateInput = document.getElementById('specific-date-filter');
  if (specificDateInput) {
    specificDateInput.addEventListener('change', e => {
      state.specificDate = e.target.value;  // YYYY-MM-DD
      // 사용자 정책: 일자 input에서 날짜 선택 시 기간 필터를 'specific'으로 자동 변경
      if (state.specificDate) {
        state.dateFilter = 'specific';
        const dateSelect = document.getElementById('date-filter');
        if (dateSelect) dateSelect.value = 'specific';
      }
      renderContent();
    });
  }
  document.getElementById('lang-filter').addEventListener('change', e => {
    state.langFilter = e.target.value;
    renderContent();
  });
  // v2.7.1: 정렬 기준 dropdown
  const sortSel = document.getElementById('sort-filter');
  if (sortSel) {
    sortSel.value = state.sortBy;
    sortSel.addEventListener('change', e => {
      state.sortBy = e.target.value;
      renderContent();
    });
  }

  // 다중 선택 — 카드 체크박스 (delegation)
  document.getElementById('news-grid').addEventListener('change', e => {
    if (e.target.classList.contains('card-check')) {
      const url = e.target.dataset.url;
      if (url) toggleSelection(url);
    }
  });

  // 선택 해제
  const btnClear = document.getElementById('btn-clear-selection');
  if (btnClear) btnClear.addEventListener('click', clearSelection);

  // 소스 현황 기간 selector — v3.0: 상단 stat-row도 함께 갱신
  const sourcesPeriodSel = document.getElementById('sources-period');
  if (sourcesPeriodSel) {
    sourcesPeriodSel.value = state.sourcesPeriod;
    sourcesPeriodSel.addEventListener('change', e => {
      state.sourcesPeriod = e.target.value;
      renderStats();
      renderSourcesStatus();
    });
  }

  // 추이 차트 view 토글 (소스별 / 카테고리별)
  document.querySelectorAll('.trend-view-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.trend-view-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.trendView = btn.dataset.trendView;
      renderSourceTrend();
    });
  });

  // 검색결과 전체 선택
  const btnSelectSearch = document.getElementById('btn-select-search-results');
  if (btnSelectSearch) btnSelectSearch.addEventListener('click', selectSearchResults);

  // AI 분석 버튼 → 모달 열기
  const btnAnalyze = document.getElementById('btn-ai-analyze');
  if (btnAnalyze) btnAnalyze.addEventListener('click', openAnalyzeModal);

  // 모달 닫기 (backdrop, X 버튼, 닫기 버튼)
  document.querySelectorAll('[data-close]').forEach(el => {
    el.addEventListener('click', closeAnalyzeModal);
  });

  // 모달 — 백엔드 탭
  document.querySelectorAll('.backend-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.backend-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.analyzeBackend = btn.dataset.backend;
      populateModelSelect();   // 모델 드롭다운 백엔드 따라 갱신
    });
  });

  // 모달 — 모델 선택
  const modelSel = document.getElementById('model-select');
  if (modelSel) {
    modelSel.addEventListener('change', e => {
      state.analyzeModel = e.target.value;
      updateModelHint();
    });
  }

  // 모달 — 프롬프트 프리셋
  const presetSel = document.getElementById('prompt-preset');
  if (presetSel) {
    presetSel.addEventListener('change', e => {
      state.analyzePromptPreset = e.target.value;
      applyPromptPreset();
    });
  }

  // 모달 — 선택 미리보기 토글
  const btnTogglePreview = document.getElementById('btn-toggle-preview');
  if (btnTogglePreview) {
    btnTogglePreview.addEventListener('click', () => {
      document.getElementById('analyze-preview-list').classList.toggle('hidden');
    });
  }

  // 모달 — 분석 실행
  const btnRun = document.getElementById('btn-run-analyze');
  if (btnRun) btnRun.addEventListener('click', runAnalysis);

  // 모달 — 결과 복사
  const btnCopy = document.getElementById('btn-copy-result');
  if (btnCopy) btnCopy.addEventListener('click', copyAnalyzeResult);

  // 본인 API 키 — 저장소 복원 (session 우선, fallback localStorage)
  // v6.0 (P1-4): session-only 토글 지원. session에 있으면 그것, 없으면 localStorage 사용.
  try {
    const fromSession = sessionStorage.getItem('daibfy_user_api_key');
    const fromLocal = localStorage.getItem('daibfy_user_api_key');
    const saved = fromSession || fromLocal;
    const input = document.getElementById('user-api-key');
    const sessionToggle = document.getElementById('user-api-key-session-only');
    if (input && saved) input.value = saved;
    // 저장소 상태로 토글 초기화: localStorage에만 있으면 영구(unchecked), 그 외엔 session(checked)
    if (sessionToggle) {
      sessionToggle.checked = !fromLocal || !!fromSession;
      const hint = document.getElementById('user-api-key-storage-hint');
      if (hint) {
        hint.textContent = sessionToggle.checked
          ? '현재: 세션 메모리에만 저장됩니다. 새로고침해도 유지되지만 브라우저 종료 시 삭제됩니다.'
          : '현재: localStorage에 영구 저장됩니다. 같은 브라우저로 돌아오면 자동 복원되지만, DevTools로 누구나 열람할 수 있습니다.';
      }
      sessionToggle.addEventListener('change', () => {
        const hintEl = document.getElementById('user-api-key-storage-hint');
        if (hintEl) {
          hintEl.textContent = sessionToggle.checked
            ? '현재: 세션 메모리에만 저장됩니다. 새로고침해도 유지되지만 브라우저 종료 시 삭제됩니다.'
            : '현재: localStorage에 영구 저장됩니다. 같은 브라우저로 돌아오면 자동 복원되지만, DevTools로 누구나 열람할 수 있습니다.';
        }
        // 토글 변경 시 즉시 저장소 정리 (혼선 방지)
        const k = (document.getElementById('user-api-key') || {}).value || '';
        if (!k) return;
        if (sessionToggle.checked) {
          try { sessionStorage.setItem('daibfy_user_api_key', k); } catch (e) {}
          try { localStorage.removeItem('daibfy_user_api_key'); } catch (e) {}
        } else {
          try { localStorage.setItem('daibfy_user_api_key', k); } catch (e) {}
          try { sessionStorage.removeItem('daibfy_user_api_key'); } catch (e) {}
        }
      });
    }
  } catch (e) {}
}

// ========================= 논문 흐름 분석 =========================

function getPapersTrendsFor(period, key) {
  // history 우선, 없으면 paper_trends.json (= 기본 weekly) 사용
  if (state.paperTrendsHistory && state.paperTrendsHistory[period]) {
    const bucket = state.paperTrendsHistory[period];
    const keys = Object.keys(bucket).sort().reverse();
    const useKey = (key && keys.includes(key)) ? key : keys[0];
    if (useKey) return { trends: bucket[useKey], key: useKey, keys };
  }
  // fallback
  if (period === (state.paperTrends && state.paperTrends.period || 'weekly')) {
    return { trends: state.paperTrends, key: null, keys: [] };
  }
  return { trends: null, key: null, keys: [] };
}

function renderPapersControls() {
  const period = state.papersPeriod;
  // 탭 active 표시
  document.querySelectorAll('[data-papers-period]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.papersPeriod === period);
  });
  const { keys, key } = getPapersTrendsFor(period, state.papersKey);
  const sel = document.getElementById('papers-period-select');
  if (sel) {
    if (!keys || keys.length === 0) {
      sel.innerHTML = '<option>—</option>';
      sel.disabled = true;
    } else {
      sel.disabled = false;
      sel.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
      if (key) sel.value = key;
    }
  }
}

function renderPapersView() {
  renderPapersControls();
  const { trends: t } = getPapersTrendsFor(state.papersPeriod, state.papersKey);
  const trends = t || state.paperTrends;
  const metaInline = document.getElementById('papers-meta-inline');
  if (!trends || !trends.paper_count) {
    if (metaInline) metaInline.innerHTML = '<span class="papers-meta-empty">아직 분석 데이터가 없습니다</span>';
    document.getElementById('papers-narrative').innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📑</div>
        <div class="empty-title">논문 흐름 분석이 아직 없습니다</div>
        <div class="empty-desc">다음 빌드(매일 KST 06:00)부터 자동 생성됩니다.</div>
      </div>`;
    document.getElementById('papers-hot-topics').innerHTML = '';
    document.getElementById('papers-techniques').innerHTML = '';
    document.getElementById('papers-institutions').innerHTML = '';
    document.getElementById('papers-keywords').innerHTML = '';
    document.getElementById('papers-actionable').innerHTML = '';
    document.getElementById('papers-list').innerHTML = '';
    return;
  }

  // v2.8.5: 인라인 메타 (탭과 같은 행) — paper_count + 기간 라벨
  if (metaInline) {
    metaInline.innerHTML = `<strong>${trends.paper_count}</strong>편 논문 · 최근 <strong>${trends.days_window}</strong>일 분석`;
  }

  // Narrative
  // v3.2: papers narrative는 헤더를 본문 사이즈 + bold inline으로 표시 (사용자 정책)
  document.getElementById('papers-narrative').innerHTML = renderMarkdown(trends.narrative || '', { inlineHeaders: true });

  // 관련 논문 드롭다운 헬퍼
  const renderPapersBlock = (papers) => {
    if (!Array.isArray(papers) || papers.length === 0) return '';
    return `
      <details class="topic-papers">
        <summary>관련 논문 ${papers.length}편 ▾</summary>
        <ol class="topic-paper-list">
          ${papers.map(p => `
            <li>
              <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
              <span class="topic-paper-meta">— ${escapeHtml(p.source || 'arXiv')} · ${escapeHtml(p.date || '')}</span>
            </li>
          `).join('')}
        </ol>
      </details>
    `;
  };

  // v3.5: Hot topics / Key techniques
  //   - 우측 상단의 N편 카운트 제거 (좌측 하단 '관련 논문 N편'만 유지)
  //   - description에 형광펜 사용 안 함 → escapeHtml만 (mark 변환 X)
  //   - topic 이름에서도 mark 제거 — bold 없는 평문
  const topicsRoot = document.getElementById('papers-hot-topics');
  const topics = trends.hot_topics || [];
  topicsRoot.innerHTML = topics.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : topics.map(t => `
        <div class="topic-item">
          <div class="topic-head">
            <span class="topic-name">${escapeHtml(t.topic || '')}</span>
          </div>
          <div class="topic-desc">${escapeHtml(t.description || '')}</div>
          ${renderPapersBlock(t.papers)}
        </div>
      `).join('');

  // Techniques — v3.5: 동일 정책
  const techRoot = document.getElementById('papers-techniques');
  const techs = trends.key_techniques || [];
  techRoot.innerHTML = techs.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : techs.map(t => `
        <div class="topic-item">
          <div class="topic-head">
            <span class="topic-name">${escapeHtml(t.technique || '')}</span>
          </div>
          <div class="topic-desc">${escapeHtml(t.description || '')}</div>
          ${renderPapersBlock(t.papers)}
        </div>
      `).join('');

  // Institutions
  const instRoot = document.getElementById('papers-institutions');
  const insts = trends.top_institutions || [];
  instRoot.innerHTML = insts.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : `<div class="freq-list">${
        insts.map(i => `
          <div class="freq-item">
            <span class="freq-name">${escapeHtml(i.name)}</span>
            <span class="freq-bar" style="width:${Math.min(100, i.count * 10)}%"></span>
            <span class="freq-count">${i.count}</span>
          </div>
        `).join('')
      }</div>`;

  // Keywords
  const kwRoot = document.getElementById('papers-keywords');
  const kws = (trends.top_keywords || []).slice(0, 15);
  kwRoot.innerHTML = kws.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : `<div class="kw-cloud">${
        kws.map(k => `<span class="kw-tag" style="font-size:${Math.min(18, 11 + k.count)}px">${escapeHtml(k.keyword)} <em>${k.count}</em></span>`).join('')
      }</div>`;

  // Actionable insights — **굵게** → <mark> 하이라이트
  const actRoot = document.getElementById('papers-actionable');
  const acts = trends.actionable_insights || [];
  actRoot.innerHTML = acts.length === 0
    ? '<li class="papers-empty">데이터 없음</li>'
    : acts.map(a => `<li>${escapeHtmlWithMark(a)}</li>`).join('');

  // 논문 목록
  const listRoot = document.getElementById('papers-list');
  const papers = trends.recent_papers || [];
  listRoot.innerHTML = papers.length === 0
    ? '<div class="papers-empty">논문 없음</div>'
    : papers.map(p => `
        <div class="paper-row">
          <div class="paper-row-head">
            <span class="score-badge mid">중요도 ${p.score || 0}</span>
            <span class="date-text" title="발행일">${escapeHtml(p.date || '—')}</span>
          </div>
          <a class="paper-row-title" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
          ${p.summary_ko ? `<div class="paper-row-summary">${escapeHtml(p.summary_ko)}</div>` : ''}
          <div class="paper-row-source">${escapeHtml(p.source || 'arXiv')}</div>
        </div>
      `).join('');
}

// ========================= 다중 선택 + AI 분석 =========================

function toggleSelection(url) {
  if (state.selectedUrls.has(url)) {
    state.selectedUrls.delete(url);
  } else {
    state.selectedUrls.add(url);
  }
  updateSelectBar();
  // 카드 시각 업데이트
  const card = document.querySelector(`.news-card[data-url="${cssEscape(url)}"]`);
  if (card) card.classList.toggle('is-selected', state.selectedUrls.has(url));
}

// v3.0: trend 카드 선택 — selectedUrls와 별도 Set으로 관리
function toggleTrendSelection(cardKey) {
  if (state.selectedTrends.has(cardKey)) {
    state.selectedTrends.delete(cardKey);
  } else {
    state.selectedTrends.add(cardKey);
  }
  updateSelectBar();
  const card = document.querySelector(`.strategy-card[data-trend-key="${cssEscape(cardKey)}"]`);
  if (card) card.classList.toggle('is-selected', state.selectedTrends.has(cardKey));
}

function clearSelection() {
  state.selectedUrls.clear();
  state.selectedTrends.clear();  // v3.0
  document.querySelectorAll('.news-card.is-selected').forEach(c => c.classList.remove('is-selected'));
  document.querySelectorAll('.strategy-card.is-selected').forEach(c => c.classList.remove('is-selected'));
  document.querySelectorAll('.card-check:checked, .trend-check:checked').forEach(c => c.checked = false);
  updateSelectBar();
}

// v3.3: 검색어를 동의어와 함께 OR로 확장 (한↔영 자동 매핑)
const SEARCH_SYNONYMS = {
  '거버넌스': ['governance'],
  'governance': ['거버넌스'],
  '에이전트': ['agent', 'agentic'],
  'agent': ['에이전트', 'agentic'],
  'agentic': ['에이전트', 'agent'],
  '리스크': ['risk'],
  'risk': ['리스크'],
  '규제': ['regulation', 'regulatory'],
  'regulation': ['규제'],
  'regulatory': ['규제'],
  '평가': ['evaluation', 'eval', 'benchmark'],
  'evaluation': ['평가', 'eval', 'benchmark'],
  'benchmark': ['평가', '벤치마크'],
  '벤치마크': ['benchmark'],
  '시사점': ['insight', 'implication'],
  'insight': ['시사점'],
  '리걸테크': ['legaltech', 'legal tech', 'legal ai'],
  'legaltech': ['리걸테크'],
  '로펌': ['law firm', 'biglaw'],
  'law firm': ['로펌'],
  '인공지능': ['ai', 'artificial intelligence'],
  'ai': ['인공지능'],
  '모델': ['model', 'llm'],
  '한국': ['korea', 'korean'],
  'korea': ['한국'],
  '투자': ['funding', 'investment', 'raises'],
  'funding': ['투자', '자금'],
  '정책': ['policy'],
  'policy': ['정책'],
  '계약': ['contract'],
  'contract': ['계약'],
  '오픈소스': ['open source', 'open-source', 'oss', 'open weight', '오픈웨이트'],
  'open source': ['오픈소스', 'open-source', 'oss'],
  'oss': ['오픈소스', 'open source'],
  '검색': ['retrieval', 'search'],
  'rag': ['검색-증강 생성', '검색 증강', '리트리벌'],
  '소송': ['litigation', 'lawsuit'],
  'litigation': ['소송'],
  // v3.8: AI 엔지니어링·인프라 동의어
  '오케스트레이션': ['orchestration', 'orchestrator', '오케스트레이터'],
  'orchestration': ['오케스트레이션', 'orchestrator', '오케스트레이터'],
  'orchestrator': ['오케스트레이터', 'orchestration', '오케스트레이션'],
  '오케스트레이터': ['orchestrator', 'orchestration', '오케스트레이션'],
  '프롬프트 엔지니어링': ['prompt engineering'],
  'prompt engineering': ['프롬프트 엔지니어링'],
  '컨텍스트 엔지니어링': ['context engineering'],
  'context engineering': ['컨텍스트 엔지니어링'],
  '하네스 엔지니어링': ['harness engineering'],
  'harness engineering': ['하네스 엔지니어링'],
  '클론 엔지니어링': ['clone engineering'],
  'clone engineering': ['클론 엔지니어링'],
  'fde': ['forward deployed engineer', '포워드 디플로이드'],
  'forward deployed engineer': ['fde', '포워드 디플로이드'],
  '포워드 디플로이드': ['fde', 'forward deployed engineer'],
  '멀티 에이전트': ['multi-agent', 'multi agent', 'multiagent'],
  'multi-agent': ['멀티 에이전트', 'multi agent'],
};
function expandSearchQuery(q) {
  if (!q) return [q];
  const lower = q.toLowerCase().trim();
  const syns = SEARCH_SYNONYMS[lower];
  if (!syns) return [lower];
  // 원본 + 동의어 모두 반환 (lowercase)
  return [lower, ...syns.map(s => s.toLowerCase())];
}
// 검색 매칭: 원본 또는 동의어 중 하나라도 텍스트에 있으면 true
function matchSearchQuery(text, q) {
  if (!q) return true;
  const terms = expandSearchQuery(q);
  const t = (text || '').toLowerCase();
  return terms.some(term => t.includes(term));
}

function selectSearchResults() {
  // v3.3: view에 따라 분기 — 저장한 항목 페이지의 시사점 탭에서는 시사점 검색 결과를 selectedTrends에
  if (state.view === 'saved' && state.savedTab === 'insights') {
    const q = (state.search || '').toLowerCase().trim();
    const entries = Object.entries(state.saved.strategy || {});
    for (const [k, entry] of entries) {
      const card = (entry && entry.card) || {};
      const blob = [card.tag, card.title, card.body, card.action,
        ...(Array.isArray(card.citations) ? card.citations.map(c => c.title + ' ' + c.source) : [])
      ].filter(Boolean).join(' ');
      if (!q || matchSearchQuery(blob, q)) {
        state.selectedTrends.add(k);
      }
    }
    renderContent();
    updateSelectBar();
    return;
  }
  // 일반 뉴스 카드 검색 결과 선택
  const visible = filterItems();
  visible.forEach(it => state.selectedUrls.add(it.url));
  renderContent();
  updateSelectBar();
}

function updateSelectBar() {
  const bar = document.getElementById('select-bar');
  // v3.0: 뉴스 카드 + trend 카드 합산
  const newsCount = state.selectedUrls.size;
  const trendCount = state.selectedTrends.size;
  const total = newsCount + trendCount;
  const label = trendCount > 0
    ? `${total}개 선택 (뉴스 ${newsCount} · 시사점 ${trendCount})`
    : `${total}개 선택`;
  document.getElementById('selected-count').textContent = label;
  if (total > 0) {
    bar.classList.remove('hidden');
  } else {
    bar.classList.add('hidden');
  }

  // 검색결과 전체 선택 버튼 — 검색어 있을 때만 표시
  const btnSelectSearch = document.getElementById('btn-select-search-results');
  if (btnSelectSearch) {
    btnSelectSearch.classList.toggle('hidden', !state.search);
  }
}

// v3.0: 선택된 trend들을 펼쳐서 analysis items 리스트 구성
//   각 trend는 (1) trend 본문 + (2) 링크된 근거 기사들로 분해되어 별도 항목으로 포함
function buildAnalysisItems() {
  const items = [];
  // 1. 뉴스 카드 (URL 기반)
  for (const it of (state.data.items || [])) {
    if (state.selectedUrls.has(it.url)) {
      items.push({
        kind: 'news',
        title: it.title,
        source: it.source,
        date: (it.date || '').slice(0, 10),
        url: it.url,
        summary: it.summary_ko || it.summary || '',
      });
    }
  }
  // 2. trend 카드 (cardKey 기반)
  const seenCitationUrls = new Set();  // 동일 근거 기사 중복 방지
  for (const key of state.selectedTrends) {
    const entry = (state.trendCardMap || {})[key];
    if (!entry) continue;
    const card = entry.card;
    // 2-a. trend 본문 자체를 1개 항목으로
    const bodyText = [card.body, card.action ? `[ACTION] ${card.action}` : ''].filter(Boolean).join('\n');
    items.push({
      kind: 'trend',
      title: `[시사점] ${card.title || ''}`,
      source: `${entry.period} ${entry.periodKey}`,
      date: entry.periodKey || '',
      url: '',
      summary: bodyText,
    });
    // 2-b. trend 작성 근거 기사들 각각을 별도 항목으로
    const cites = Array.isArray(card.citations) ? card.citations : [];
    for (const c of cites) {
      if (!c.url || seenCitationUrls.has(c.url)) continue;
      seenCitationUrls.add(c.url);
      items.push({
        kind: 'citation',
        title: c.title || '',
        source: c.source || '',
        date: (c.date || '').slice(0, 10),
        url: c.url,
        summary: '',  // citation은 원본 기사이지만 enriched_news에 별도 summary 안 가지고 있음
      });
    }
  }
  return items;
}

function openAnalyzeModal() {
  if (state.selectedUrls.size === 0 && state.selectedTrends.size === 0) {
    alert('먼저 카드를 선택해주세요.');
    return;
  }
  const modal = document.getElementById('analyze-modal');
  modal.classList.remove('hidden');

  // v3.0: 뉴스 + trend(+근거) 펼친 전체 items
  const items = buildAnalysisItems();
  const newsN = items.filter(i => i.kind === 'news').length;
  const trendN = items.filter(i => i.kind === 'trend').length;
  const citationN = items.filter(i => i.kind === 'citation').length;
  document.getElementById('analyze-count').textContent =
    trendN > 0
      ? `${items.length}개 항목 (뉴스 ${newsN} · 시사점 ${trendN} · 근거 ${citationN})`
      : `${items.length}개 항목 선택`;
  const list = document.getElementById('analyze-preview-list');
  const kindBadge = (k) => k === 'trend' ? '<span class="rel-kind kind-trend">시사점</span>' : k === 'citation' ? '<span class="rel-kind kind-citation">근거</span>' : '';
  list.innerHTML = items.map(i => `<li>${kindBadge(i.kind)} ${escapeHtml(i.title)} <span class="rel-source">— ${escapeHtml(i.source)}</span></li>`).join('');

  // 모델 드롭다운 채우기
  populateModelSelect();

  // 프롬프트 기본값
  applyPromptPreset();

  // 결과 영역 초기화
  const resultWrap = document.getElementById('analyze-result-wrap');
  resultWrap.classList.add('hidden');
  document.getElementById('analyze-result').innerHTML = '';
  document.getElementById('analyze-meta').textContent = '';
}

function populateModelSelect() {
  const sel = document.getElementById('model-select');
  if (!sel) return;
  const models = MODELS[state.analyzeBackend] || [];
  sel.innerHTML = models.map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.label)}</option>`).join('');

  // state.analyzeModel이 현재 백엔드에 없으면 기본값 (첫 모델)로
  const ids = models.map(m => m.id);
  if (!ids.includes(state.analyzeModel)) {
    state.analyzeModel = ids[0];
  }
  sel.value = state.analyzeModel;
  updateModelHint();
}

function updateModelHint() {
  const hintEl = document.getElementById('model-hint');
  if (!hintEl) return;
  const m = (MODELS[state.analyzeBackend] || []).find(x => x.id === state.analyzeModel);
  hintEl.textContent = m ? m.hint : '';
}

function closeAnalyzeModal() {
  document.getElementById('analyze-modal').classList.add('hidden');
}

function applyPromptPreset() {
  const preset = state.analyzePromptPreset;
  const input = document.getElementById('prompt-input');
  if (preset !== 'custom') {
    input.value = PROMPT_PRESETS[preset] || '';
  }
}

async function runAnalysis() {
  // v3.0: 뉴스 + trend + 근거 기사 통합 항목 사용
  const items = buildAnalysisItems();
  if (items.length === 0) {
    alert('선택된 항목이 없습니다.');
    return;
  }

  const promptInstruction = document.getElementById('prompt-input').value.trim();
  if (!promptInstruction) {
    alert('분석 요청을 입력해주세요.');
    return;
  }

  // v3.0: kind별 라벨 붙여서 프롬프트 구성 (LLM이 시사점/근거를 구분해서 이해하도록)
  const kindLabel = (k) => k === 'trend' ? '시사점' : k === 'citation' ? '시사점 근거' : '뉴스';
  const blob = items.slice(0, 80).map((it, i) => {
    const summary = (it.summary || '').slice(0, 300);
    const meta = [it.source, it.date].filter(Boolean).join(', ');
    const urlLine = it.url ? `   URL: ${it.url}` : '';
    return `${i + 1}. [${kindLabel(it.kind)}|${meta}] ${it.title}\n   ${summary}${urlLine ? '\n' + urlLine : ''}`;
  }).join('\n\n');

  const trendN = items.filter(i => i.kind === 'trend').length;
  const newsN = items.filter(i => i.kind !== 'trend').length;
  const header = trendN > 0
    ? `[분석 대상] 시사점 ${trendN}건 + 뉴스/근거 ${newsN}건 (총 ${items.length}건)`
    : `[분석 대상 뉴스 ${items.length}건]`;
  const fullPrompt = `${promptInstruction}\n\n${header}\n\n${blob}`;

  // 본인 API 키 (옵션)
  // v6.0 (P1-4): session-only 토글에 따라 sessionStorage / localStorage 선택 저장
  const userKey = document.getElementById('user-api-key').value.trim();
  if (userKey) {
    const sessionOnly = !!(document.getElementById('user-api-key-session-only') || {}).checked;
    try {
      if (sessionOnly) {
        sessionStorage.setItem('daibfy_user_api_key', userKey);
        localStorage.removeItem('daibfy_user_api_key');
      } else {
        localStorage.setItem('daibfy_user_api_key', userKey);
        sessionStorage.removeItem('daibfy_user_api_key');
      }
    } catch (e) {}
  }

  const headers = { 'Content-Type': 'application/json' };
  if (userKey) {
    headers['X-User-Api-Key'] = userKey;
    headers['X-User-Backend'] = state.analyzeBackend;
  }

  const runBtn = document.getElementById('btn-run-analyze');
  const resultWrap = document.getElementById('analyze-result-wrap');
  const resultEl = document.getElementById('analyze-result');
  const metaEl = document.getElementById('analyze-meta');

  runBtn.disabled = true;
  runBtn.textContent = '분석 중...';
  resultWrap.classList.remove('hidden');
  resultEl.innerHTML = '<div class="analyze-loading">🤖 모델 연결 중<span class="dots"></span></div>';
  metaEl.textContent = '';

  // v2.7.2: SSE 스트리밍 — 첫 글자가 1~2초 안에 도착, 타이핑하듯 누적
  try {
    const t0 = Date.now();
    let firstByteTime = null;
    const r = await fetch(WORKER_ENDPOINT, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        backend: state.analyzeBackend,
        model: state.analyzeModel,
        prompt: fullPrompt,
        max_tokens: 8000,  // v3.4: 답변이 잘리지 않도록 상향 (2500 → 8000)
        stream: true,  // ← 스트리밍 요청
      }),
    });
    if (!r.ok) {
      // 비-스트리밍 에러 응답
      let data;
      try { data = await r.json(); } catch (e) { data = { error: `HTTP ${r.status}` }; }
      const msg = data.error || `HTTP ${r.status}`;
      if (data.limit_reached) {
        resultEl.innerHTML = `
          <div class="analyze-error">
            <strong>${escapeHtml(msg)}</strong>
            <p>본인 API 키를 입력하시면 한도 제한 없이 사용할 수 있습니다.</p>
          </div>
        `;
      } else {
        resultEl.innerHTML = `<div class="analyze-error"><strong>분석 실패</strong><p>${escapeHtml(msg)}</p></div>`;
      }
      return;
    }

    // 스트리밍 응답 처리
    const contentType = r.headers.get('Content-Type') || '';
    if (!contentType.includes('text/event-stream')) {
      // Worker가 옛 버전이면 JSON으로 폴백
      const data = await r.json();
      resultEl.innerHTML = renderMarkdown(data.result || '');
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      const usage = data.usage || {};
      metaEl.textContent = `${data.backend} · ${data.model} · ${elapsed}초 · 입력 ${usage.input_tokens || usage.prompt_tokens || '?'}토큰 / 출력 ${usage.output_tokens || usage.completion_tokens || '?'}토큰`;
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';
    let meta = { backend: state.analyzeBackend, model: state.analyzeModel, used_user_key: false };
    let usage = {};
    let streamErr = null;

    resultEl.innerHTML = '<div class="analyze-stream"></div>';
    const streamEl = resultEl.querySelector('.analyze-stream');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const evt of events) {
        const dataLine = evt.split('\n').find(l => l.startsWith('data:'));
        if (!dataLine) continue;
        const payload = dataLine.slice(5).trim();
        if (!payload) continue;
        try {
          const parsed = JSON.parse(payload);
          if (parsed.type === 'meta') {
            meta = { ...meta, ...parsed };
            if (firstByteTime === null) firstByteTime = Date.now();
            metaEl.textContent = `${meta.backend} · ${meta.model} · 응답 수신 시작…`;
          } else if (parsed.type === 'delta' && parsed.text) {
            if (firstByteTime === null) {
              firstByteTime = Date.now();
              const ttfb = ((firstByteTime - t0) / 1000).toFixed(1);
              metaEl.textContent = `${meta.backend} · ${meta.model} · TTFB ${ttfb}초 · 생성 중…`;
            }
            accumulated += parsed.text;
            streamEl.innerHTML = renderMarkdown(accumulated) + '<span class="stream-cursor">▌</span>';
            // 자동 스크롤
            resultEl.scrollTop = resultEl.scrollHeight;
          } else if (parsed.type === 'done') {
            usage = parsed.usage || {};
            meta.model = parsed.model || meta.model;
          } else if (parsed.type === 'error') {
            streamErr = parsed.error;
          }
        } catch (e) { /* incomplete chunk */ }
      }
    }

    // 완료
    streamEl.innerHTML = renderMarkdown(accumulated);
    if (streamErr) {
      streamEl.innerHTML += `<div class="analyze-error"><strong>스트림 오류</strong><p>${escapeHtml(streamErr)}</p></div>`;
    }
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const ttfb = firstByteTime ? ((firstByteTime - t0) / 1000).toFixed(1) : '?';
    const inT = usage.input_tokens || usage.prompt_tokens || '?';
    const outT = usage.output_tokens || usage.completion_tokens || '?';
    metaEl.textContent = `${meta.backend} · ${meta.model} · 첫 응답 ${ttfb}초 / 전체 ${elapsed}초 · 입력 ${inT}토큰 / 출력 ${outT}토큰` + (meta.used_user_key ? ' · 본인 키' : '');

    // v2.7.5: 분석 성공 시 history에 저장 (AI 분석 결과 페이지에서 다시 볼 수 있도록)
    if (accumulated && !streamErr) {
      saveAnalysis({
        id: 'a' + Date.now() + Math.random().toString(36).slice(2, 6),
        timestamp: Date.now(),
        backend: meta.backend,
        model: meta.model,
        promptPreset: state.analyzePromptPreset,
        promptText: promptInstruction,
        items: items.slice(0, 80).map(it => ({
          title: it.title, url: it.url, source: it.source,
          date: it.date, kind: it.kind,
        })),
        result: accumulated,
        usage: { input: inT, output: outT },
        ttfbSec: parseFloat(ttfb), totalSec: parseFloat(elapsed),
      });
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="analyze-error"><strong>네트워크 오류</strong><p>${escapeHtml(e.message || String(e))}</p><p>Worker URL이 살아있는지, CORS가 허용되는지 확인하세요.</p></div>`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '분석 실행';
  }
}

// v6.0 (P2-3): UNBOLD_PROPER_NOUNS / _escapeRegex / unboldProperNouns /
//              PAPERS_NARRATIVE_LABELS / renderMarkdown 는 app.util.js로 이동됨.

function copyAnalyzeResult() {
  const result = document.getElementById('analyze-result').innerText;
  if (!result) return;
  navigator.clipboard.writeText(result).then(() => {
    const btn = document.getElementById('btn-copy-result');
    const orig = btn.textContent;
    btn.textContent = '✓ 복사됨';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

// v6.0 (P2-3): cssEscape / isNewToday 는 app.util.js로 이동됨.
// ========================= Phase 2b: 엔티티 뷰 =========================

const ENTITY_TYPE_LABEL = {
  ai_company: 'AI 회사',
  legaltech_company: '리걸테크',
  korean_law_firm: '한국 로펌',
  global_law_firm: '글로벌 로펌',
  korean_finance: '한국 금융',
  korean_manufacturing: '한국 제조',
  kr_government: '정부 부처',
  policy: '정책·법안',
  tech: '기술',
  ai_product: 'AI 제품',
  benchmark: '벤치마크',
  academic_inst: '학술·연구 기관',  // v5.2
  researcher: '연구자',              // v5.2
};

const ENTITY_TYPE_ORDER = [
  'ai_company', 'legaltech_company', 'korean_law_firm', 'global_law_firm',
  'korean_finance', 'korean_manufacturing', 'kr_government', 'policy',
  'ai_product', 'benchmark', 'academic_inst', 'researcher', 'tech',
];

async function loadEntities() {
  if (state.entities) return state.entities;
  try {
    // v6.0 (P2-1): 빌드 버전 기반 cache-buster (state.buildVersion에 init() 단계에서 저장)
    const v = state.buildVersion || Date.now();
    const r = await fetch('data/entities.json?v=' + encodeURIComponent(v), { cache: 'default' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    state.entities = await r.json();
    return state.entities;
  } catch (e) {
    console.error('[entities] load failed:', e);
    state.entities = { entities: {}, total_entities: 0, error: String(e) };
    return state.entities;
  }
}

// Phase 3: relations.json 로드 + 엔티티별 인덱스 구축
async function loadRelations() {
  if (state.relations) return state.relations;
  try {
    const v = state.buildVersion || Date.now();
    const r = await fetch('data/relations.json?v=' + encodeURIComponent(v), { cache: 'default' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    state.relations = await r.json();
  } catch (e) {
    console.warn('[relations] load failed (다음 빌드에서 생성됨):', e);
    state.relations = { relations: [], total_relations: 0, error: String(e) };
  }
  // 엔티티별 인덱스 (양방향) — v5.0: source_type, trend_period/key 보존
  const idx = {};
  for (const r of (state.relations.relations || [])) {
    if (!idx[r.source]) idx[r.source] = [];
    if (!idx[r.target]) idx[r.target] = [];
    const base = {
      type: r.type, evidence: r.evidence, weight: r.weight,
      source_type: r.source_type || 'trend',
      trend_tag: r.trend_tag, trend_period: r.trend_period, trend_key: r.trend_key,
    };
    idx[r.source].push({ otherId: r.target, dir: 'out', ...base });
    idx[r.target].push({ otherId: r.source, dir: 'in', ...base });
  }
  state.relationsByEntity = idx;
  return state.relations;
}

// v5.0: 대칭 관계 타입 (방향 무관)
const SYMMETRIC_RELATION_TYPES = new Set(['competes_with', 'partners_with', 'mentions']);

// v5.0: 엔티티별 mention 카운트 (논문 토글 적용)
function entityEffectiveMentions(e) {
  if (!e) return 0;
  const articles = (e.mentioned_articles || []).length;
  const trends = (e.mentioned_trends || []).length;
  const papers = (e.mentioned_papers || []).length;
  return state.entityIncludePapers ? (articles + trends + papers) : (articles + trends);
}

// Phase 3: 관계 타입 라벨 (한국어)
const RELATION_TYPE_LABEL = {
  competes_with: '경쟁',
  partners_with: '제휴',
  acquires: '인수',
  invests_in: '투자',
  regulates: '규제',
  adopts: '도입',
  launches: '출시',
  implements: '정책',
  mentions: '언급',
};
const RELATION_TYPE_COLOR = {
  competes_with: '#e15759',
  partners_with: '#4e9aaf',
  acquires: '#76b7b2',
  invests_in: '#59a14f',
  regulates: '#a86ec9',
  adopts: '#edc949',
  launches: '#f28e2b',
  implements: '#9c755f',
  mentions: '#bab0ab',
};
const ENTITY_TYPE_COLOR = {
  ai_company: '#4e79a7',
  legaltech_company: '#76b7b2',
  korean_law_firm: '#e15759',
  global_law_firm: '#af7aa1',
  korean_finance: '#edc949',
  korean_manufacturing: '#f28e2b',
  kr_government: '#9c755f',
  policy: '#bab0ab',
  ai_product: '#59a14f',
  benchmark: '#ff9da7',
  tech: '#a0cbe8',
  academic_inst: '#b07aa1',  // v5.2: 보라 계열
  researcher: '#d4a373',     // v5.2: 갈색 계열
};

function renderEntitiesView() {
  const wrap = document.getElementById('entities-view');
  const listEl = document.getElementById('entities-list-wrap');
  const detailEl = document.getElementById('entity-detail-wrap');
  if (!wrap || !listEl) return;

  // 상세 화면 모드
  if (state.selectedEntityId) {
    if (listEl) listEl.classList.add('hidden');
    if (detailEl) detailEl.classList.remove('hidden');
    renderEntityDetail();
    return;
  }
  if (listEl) listEl.classList.remove('hidden');
  if (detailEl) detailEl.classList.add('hidden');

  listEl.innerHTML = '<div class="loading">엔티티 로딩 중...</div>';
  loadEntities().then(data => {
    const ents = data.entities || {};
    const entries = Object.values(ents);
    if (entries.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <p><strong>엔티티 데이터 없음</strong></p>
          <p>다음 빌드에서 자동 생성됩니다 (KST 18시 또는 수동 빌드).</p>
          ${data.error ? `<p style="color:#999">에러: ${escapeHtml(data.error)}</p>` : ''}
        </div>`;
      return;
    }
    // type별 그룹화 (논문 포함/제외 토글 반영)
    const byType = {};
    for (const e of entries) {
      const t = e.type || 'other';
      if (!byType[t]) byType[t] = [];
      byType[t].push(e);
    }
    for (const t of Object.keys(byType)) {
      byType[t].sort((a, b) => entityEffectiveMentions(b) - entityEffectiveMentions(a));
    }

    let html = '';
    html += `<div class="entities-summary">
      <span>총 <strong>${entries.length}</strong>개 엔티티 활성 · ${data.generated_at ? '생성 ' + (data.generated_at.slice(0, 16)) : ''}</span>
      <label class="entity-toggle">
        <input type="checkbox" id="entities-toggle-papers" ${state.entityIncludePapers ? 'checked' : ''}/>
        <span>논문 흐름 포함</span>
      </label>
    </div>`;
    for (const t of ENTITY_TYPE_ORDER) {
      if (!byType[t] || byType[t].length === 0) continue;
      const label = ENTITY_TYPE_LABEL[t] || t;
      html += `<div class="entity-type-section">`;
      html += `  <h3 class="entity-type-title">${label} <span class="entity-type-count">${byType[t].length}</span></h3>`;
      html += `  <div class="entity-grid">`;
      for (const e of byType[t]) {
        const effMentions = entityEffectiveMentions(e);
        html += `
          <div class="entity-card" data-entity-id="${escapeHtml(e.id)}">
            <div class="entity-name">${escapeHtml(e.name)}</div>
            <div class="entity-meta">
              <span class="entity-mentions">언급 <strong>${effMentions}</strong></span>
              <span class="entity-avgscore">평균 ${e.avg_score}</span>
            </div>
            <div class="entity-foot">
              ${e.mentioned_trends && e.mentioned_trends.length > 0 ? `<span class="entity-pill">시사점 ${e.mentioned_trends.length}</span>` : ''}
              ${state.entityIncludePapers && e.mentioned_papers && e.mentioned_papers.length > 0 ? `<span class="entity-pill">논문 ${e.mentioned_papers.length}</span>` : ''}
            </div>
          </div>`;
      }
      html += `  </div>`;
      html += `</div>`;
    }
    listEl.innerHTML = html;

    // 카드 클릭 → 상세 화면
    listEl.querySelectorAll('.entity-card').forEach(card => {
      card.addEventListener('click', () => {
        const eid = card.getAttribute('data-entity-id');
        if (eid) {
          state.selectedEntityId = eid;
          renderEntitiesView();
        }
      });
    });
    // 논문 토글 핸들러
    const togEl = document.getElementById('entities-toggle-papers');
    if (togEl) {
      togEl.addEventListener('change', (ev) => {
        state.entityIncludePapers = ev.target.checked;
        renderEntitiesView();
      });
    }
  });
}

function renderEntityDetail() {
  const detailEl = document.getElementById('entity-detail-wrap');
  if (!detailEl) return;
  const ents = (state.entities && state.entities.entities) || {};
  const e = ents[state.selectedEntityId];
  if (!e) {
    detailEl.innerHTML = '<div class="empty-state">엔티티를 찾을 수 없습니다.</div>';
    return;
  }
  const typeLabel = ENTITY_TYPE_LABEL[e.type] || e.type;
  let html = `<div class="entity-detail">`;
  html += `<button class="entity-back-btn" id="entity-back">← 목록</button>`;
  html += `<div class="entity-detail-head">
    <h2>${escapeHtml(e.name)}</h2>
    <div class="entity-detail-meta">
      <span class="entity-type-badge">${escapeHtml(typeLabel)}</span>
      <span>언급 <strong>${e.total_mentions}</strong>건</span>
      <span>평균 score <strong>${e.avg_score}</strong></span>
      ${e.first_seen ? `<span>최초 ${e.first_seen}</span>` : ''}
      ${e.last_seen ? `<span>최근 ${e.last_seen}</span>` : ''}
    </div>
  </div>`;

  // Phase 3: 관련 엔티티 (relations.json 기반) — 시사점 위에 배치 (가장 통찰력 있는 정보)
  html += `<div class="entity-section entity-relations-section" id="entity-relations-placeholder">
    <h3>🔗 관련 엔티티 <span class="entity-relations-loading">로딩 중...</span></h3>
  </div>`;

  // v5.0: 관련 시사점 — 클릭 시 해당 시사점 페이지로 이동
  if (e.mentioned_trends && e.mentioned_trends.length > 0) {
    html += `<div class="entity-section">
      <h3>📌 관련 시사점 (${e.mentioned_trends.length})</h3>
      <ul class="entity-list entity-trends-list">`;
    for (const t of e.mentioned_trends.slice(0, 15)) {
      const periodLabel = ({ daily: '일간', weekly: '주간', monthly: '월간' })[t.period] || t.period;
      html += `<li class="entity-link-row" data-nav-type="trend" data-period="${escapeHtml(t.period||'')}" data-key="${escapeHtml(t.key||'')}">
        <span class="entity-list-meta">${escapeHtml(periodLabel)} · ${escapeHtml(t.key)}</span>
        <span class="entity-link-text">${escapeHtml(t.tag || t.title || '')}</span>
      </li>`;
    }
    html += `</ul></div>`;
  }
  // v5.0: 관련 논문 흐름 — 클릭 시 논문 흐름 페이지로 이동
  if (e.mentioned_papers && e.mentioned_papers.length > 0) {
    html += `<div class="entity-section">
      <h3>📑 관련 논문 흐름 (${e.mentioned_papers.length})</h3>
      <ul class="entity-list entity-papers-list">`;
    for (const p of e.mentioned_papers.slice(0, 10)) {
      const periodLabel = ({ daily: '일간', weekly: '주간', monthly: '월간' })[p.period] || p.period;
      html += `<li class="entity-link-row" data-nav-type="paper" data-period="${escapeHtml(p.period||'')}" data-key="${escapeHtml(p.key||'')}">
        <span class="entity-list-meta">${escapeHtml(periodLabel)} · ${escapeHtml(p.key)}</span>
        <span class="entity-link-text">${p.paper_count}편 분석</span>
      </li>`;
    }
    html += `</ul></div>`;
  }
  // 관련 article (최근순, 전체)
  if (e.mentioned_articles && e.mentioned_articles.length > 0) {
    html += `<div class="entity-section">
      <h3>📰 관련 article (${e.mentioned_articles.length}건, 최근순)</h3>
      <ul class="entity-list entity-articles">`;
    for (const a of e.mentioned_articles) {
      html += `<li>
        <span class="entity-list-meta">${escapeHtml(a.date || '')} · ${escapeHtml(a.source || '')} · ${a.score || 0}점</span>
        <br/><a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.title || '')}</a>
      </li>`;
    }
    html += `</ul></div>`;
  }
  html += `</div>`;
  detailEl.innerHTML = html;

  // 목록으로 돌아가기
  const backBtn = document.getElementById('entity-back');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      state.selectedEntityId = null;
      renderEntitiesView();
    });
  }

  // 시사점/논문 행 클릭 → 해당 페이지로 navigate
  detailEl.querySelectorAll('.entity-link-row').forEach(row => {
    row.addEventListener('click', () => {
      const navType = row.getAttribute('data-nav-type');
      const period = row.getAttribute('data-period');
      const key = row.getAttribute('data-key');
      if (navType === 'trend') {
        state.view = 'strategy';
        state.strategyPeriod = period;
        state.strategyKey = key;
      } else if (navType === 'paper') {
        state.view = 'papers';
        state.papersPeriod = period;
        state.papersKey = key;
      }
      // 사이드바 nav active 토글
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      const navEl = document.querySelector(`.nav-item[data-view="${state.view}"]`);
      if (navEl) navEl.classList.add('active');
      syncUrl();  // v6.5: 엔티티 row 클릭으로 strategy/papers 이동 시도 URL 갱신
      renderContent();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  // v5.0: 관련 엔티티 — otherId 기준으로 묶고 (대칭 type은 방향 합치기), 같은 엔티티의 모든 관계 타입을 한 카드에 칩으로 표시
  loadRelations().then(() => {
    const placeholder = document.getElementById('entity-relations-placeholder');
    if (!placeholder) return;
    let rels = (state.relationsByEntity && state.relationsByEntity[state.selectedEntityId]) || [];
    // 논문 토글 적용 — source_type='paper' 제외 옵션
    if (!state.entityIncludePapers) {
      rels = rels.filter(r => (r.source_type || 'trend') !== 'paper');
    }
    // otherId로 그룹 (한 엔티티 = 한 카드)
    const byOther = {};
    for (const r of rels) {
      if (!byOther[r.otherId]) byOther[r.otherId] = { otherId: r.otherId, byType: {}, totalWeight: 0, evidences: [] };
      const g = byOther[r.otherId];
      // 같은 type은 대칭이면 방향 무관 1건, 비대칭이면 방향 구분
      const isSym = SYMMETRIC_RELATION_TYPES.has(r.type);
      const tk = isSym ? r.type : (r.type + '|' + r.dir);
      if (!g.byType[tk]) g.byType[tk] = { type: r.type, dir: isSym ? 'sym' : r.dir, count: 0, weight: 0 };
      g.byType[tk].count += 1;
      g.byType[tk].weight += r.weight || 1;
      g.totalWeight += r.weight || 1;
      if (r.evidence) g.evidences.push({ type: r.type, dir: r.dir, evidence: r.evidence });
    }
    const items = Object.values(byOther).sort((a, b) => b.totalWeight - a.totalWeight);
    if (items.length === 0) {
      placeholder.innerHTML = `<h3>🔗 관련 엔티티 <span class="entity-relations-empty">아직 추출된 관계 없음</span></h3>
        <p class="entity-relations-hint">다음 빌드에서 LLM이 시사점 카드로부터 관계를 추출합니다.</p>`;
      return;
    }
    let h = `<div class="entity-relations-head">
      <h3>🔗 관련 엔티티 (${items.length})</h3>
      <label class="entity-toggle">
        <input type="checkbox" id="entity-toggle-papers" ${state.entityIncludePapers ? 'checked' : ''}/>
        <span>논문 흐름 포함</span>
      </label>
    </div>
    <div class="entity-relations-grid">`;
    for (const g of items.slice(0, 40)) {
      const other = ents[g.otherId];
      const otherName = other ? other.name : g.otherId;
      const otherTypeLabel = other ? (ENTITY_TYPE_LABEL[other.type] || other.type) : '';
      // 관계 타입 칩들 — weight 내림차순
      const typeChips = Object.values(g.byType).sort((a, b) => b.weight - a.weight);
      // 대표 evidence — 가장 weight 큰 type의 evidence를 첫 번째로
      const primaryEv = g.evidences.length > 0 ? g.evidences[0] : null;
      let chipsHtml = '';
      for (const tc of typeChips) {
        const color = RELATION_TYPE_COLOR[tc.type] || '#999';
        const typeLabel = RELATION_TYPE_LABEL[tc.type] || tc.type;
        const dirArrow = tc.dir === 'out' ? '→' : (tc.dir === 'in' ? '←' : '↔');
        chipsHtml += `<span class="entity-relation-chip" style="background:${color}22;color:${color};border:0.5px solid ${color}44;">
          <span class="chip-arrow">${dirArrow}</span> ${escapeHtml(typeLabel)}${tc.count > 1 ? ` ${tc.count}` : ''}
        </span>`;
      }
      // evidence 묶음 (최대 2개, 서로 다른 type)
      const seenEvTypes = new Set();
      let evHtml = '';
      for (const ev of g.evidences) {
        if (seenEvTypes.has(ev.type)) continue;
        seenEvTypes.add(ev.type);
        const tColor = RELATION_TYPE_COLOR[ev.type] || '#999';
        evHtml += `<div class="entity-relation-evidence">
          <span class="evidence-type-marker" style="color:${tColor};">${RELATION_TYPE_LABEL[ev.type] || ev.type}</span>
          <span>"${escapeHtml(ev.evidence)}"</span>
        </div>`;
        if (seenEvTypes.size >= 2) break;
      }
      h += `<div class="entity-relation-card" data-other-id="${escapeHtml(g.otherId)}">
        <div class="entity-relation-head">
          <span class="entity-relation-name">${escapeHtml(otherName)}</span>
          ${otherTypeLabel ? `<span class="entity-relation-other-type">${escapeHtml(otherTypeLabel)}</span>` : ''}
        </div>
        <div class="entity-relation-chips">${chipsHtml}</div>
        ${evHtml}
      </div>`;
    }
    h += `</div>`;
    placeholder.innerHTML = h;

    // 관련 엔티티 카드 클릭 → 해당 엔티티 상세
    placeholder.querySelectorAll('.entity-relation-card').forEach(card => {
      card.addEventListener('click', () => {
        const oid = card.getAttribute('data-other-id');
        if (oid && ents[oid]) {
          state.selectedEntityId = oid;
          renderEntityDetail();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });
    });
    // 논문 토글 핸들러
    const toggleEl = document.getElementById('entity-toggle-papers');
    if (toggleEl) {
      toggleEl.addEventListener('change', (ev) => {
        state.entityIncludePapers = ev.target.checked;
        renderEntityDetail();
      });
    }
  });
}

// ========================= Phase 3: 지식그래프 (D3) =========================

function renderGraphView() {
  const wrap = document.getElementById('graph-view');
  if (!wrap) return;
  // 컨트롤 + svg 구조 한 번만 그림
  if (!wrap.querySelector('.graph-container')) {
    let controlsHtml = '<div class="graph-controls">';
    controlsHtml += '<span class="graph-controls-label">관계 타입 필터:</span>';
    controlsHtml += '<button class="graph-filter-btn active" data-type="">전체</button>';
    for (const t of Object.keys(RELATION_TYPE_LABEL)) {
      const color = RELATION_TYPE_COLOR[t] || '#999';
      controlsHtml += `<button class="graph-filter-btn" data-type="${t}" style="border-color:${color}33;color:${color}">${RELATION_TYPE_LABEL[t]}</button>`;
    }
    controlsHtml += '</div>';
    // v5.0: 옵션 토글 (논문 포함 / 고립 노드 표시)
    controlsHtml += `<div class="graph-options">
      <label class="entity-toggle">
        <input type="checkbox" id="graph-toggle-papers" ${state.entityIncludePapers ? 'checked' : ''}/>
        <span>논문 흐름 포함</span>
      </label>
      <label class="entity-toggle">
        <input type="checkbox" id="graph-toggle-isolated" ${state.graphShowIsolated ? 'checked' : ''}/>
        <span>관계 없는 엔티티도 표시</span>
      </label>
    </div>`;
    controlsHtml += '<div class="graph-meta" id="graph-meta">로딩 중...</div>';
    controlsHtml += '<div class="graph-container"><svg id="graph-svg" width="100%" height="640"><g id="graph-g"></g></svg></div>';
    controlsHtml += '<div class="graph-tip">노드 드래그 → 위치 고정 (테두리 진해짐) · 더블클릭 → 고정 해제 · 휠 줌 · 한 번 클릭 → 엔티티 상세 · 선 굵기 = 관계 강도</div>';
    wrap.innerHTML = controlsHtml;
    // 필터 버튼 핸들러
    wrap.querySelectorAll('.graph-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        wrap.querySelectorAll('.graph-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.graphTypeFilter = btn.getAttribute('data-type') || null;
        renderGraphSvg();
      });
    });
    // 옵션 토글 핸들러
    const tp = document.getElementById('graph-toggle-papers');
    const ti = document.getElementById('graph-toggle-isolated');
    if (tp) tp.addEventListener('change', (ev) => { state.entityIncludePapers = ev.target.checked; renderGraphSvg(); });
    if (ti) ti.addEventListener('change', (ev) => { state.graphShowIsolated = ev.target.checked; renderGraphSvg(); });
  }
  // 데이터 로드
  Promise.all([loadEntities(), loadRelations()]).then(() => {
    renderGraphSvg();
  });
}

function renderGraphSvg() {
  const svg = document.getElementById('graph-svg');
  const metaEl = document.getElementById('graph-meta');
  if (!svg) return;
  if (typeof d3 === 'undefined') {
    if (metaEl) metaEl.textContent = 'D3 로딩 실패 — 새로고침 후 다시 시도';
    return;
  }

  const ents = (state.entities && state.entities.entities) || {};
  const allRels = (state.relations && state.relations.relations) || [];
  if (Object.keys(ents).length === 0) {
    if (metaEl) metaEl.innerHTML = '<strong>엔티티 데이터 없음</strong> — 다음 빌드 후 표시됩니다.';
    return;
  }
  // v5.0: 필터 — 관계 타입 + 논문 source 제외
  let relsFiltered = allRels;
  if (state.graphTypeFilter) relsFiltered = relsFiltered.filter(r => r.type === state.graphTypeFilter);
  if (!state.entityIncludePapers) relsFiltered = relsFiltered.filter(r => (r.source_type || 'trend') !== 'paper');

  // 노드 선택: 기본은 관계 있는 엔티티만, 토글 시 모든 엔티티 (단, 어느 시사점/article에라도 등장한 엔티티만)
  const usedIds = new Set();
  for (const r of relsFiltered) { usedIds.add(r.source); usedIds.add(r.target); }
  if (state.graphShowIsolated) {
    for (const id of Object.keys(ents)) {
      const e = ents[id];
      const mentions = entityEffectiveMentions(e);
      if (mentions > 0) usedIds.add(id);
    }
  }
  const nodes = [];
  for (const id of usedIds) {
    if (!ents[id]) continue;
    const e = ents[id];
    nodes.push({
      id,
      name: e.name,
      type: e.type,
      mentions: entityEffectiveMentions(e) || 1,
      avgScore: e.avg_score || 0,
    });
  }
  const links = relsFiltered
    .filter(r => ents[r.source] && ents[r.target])
    .map(r => ({ source: r.source, target: r.target, type: r.type, weight: r.weight || 1 }));

  if (nodes.length === 0) {
    if (metaEl) metaEl.innerHTML = '<strong>표시할 노드가 없습니다</strong> — 필터를 조정하거나 다음 빌드를 기다리세요.';
    // SVG 초기화
    const svgSelEmpty = d3.select(svg);
    svgSelEmpty.select('#graph-g').selectAll('*').remove();
    return;
  }

  if (metaEl) {
    metaEl.innerHTML = `노드 <strong>${nodes.length}</strong> · 관계 <strong>${links.length}</strong>` +
      (state.relations.generated_at ? ` · 생성 ${state.relations.generated_at.slice(0, 16)}` : '');
  }

  // SVG 초기화
  const svgSel = d3.select(svg);
  const g = svgSel.select('#graph-g');
  g.selectAll('*').remove();

  const width = svg.clientWidth || 900;
  const height = 640;

  // 줌·팬 적용
  svgSel.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform);
  }));

  // 시뮬레이션
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(110).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-220))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide().radius(d => 14 + Math.sqrt(d.mentions || 1) * 3));

  // v6.15.5: 관계 강도(weight, 1.0~6.5)를 선 굵기 + 투명도로 강조 표현
  // 기존: sqrt(weight) capped 4 → weight 6.5도 2.55px (차이 미미)
  // 변경: linear-ish 1.5~8px + opacity 0.4~0.9
  const link = g.append('g').attr('class', 'graph-links')
    .selectAll('line').data(links).enter().append('line')
    .attr('stroke', d => RELATION_TYPE_COLOR[d.type] || '#999')
    .attr('stroke-opacity', d => {
      const w = d.weight || 1;
      return Math.min(0.92, 0.4 + (w - 1) * 0.12);  // weight 1→0.40, 3→0.64, 5→0.88, 6.5→0.92
    })
    .attr('stroke-width', d => {
      const w = d.weight || 1;
      return Math.max(1.5, Math.min(8, 1.5 + Math.sqrt(Math.max(0, w - 1)) * 2.8));
      // weight 1→1.5, 2→4.3, 3→5.5, 5→7.1, 6.5→8 (cap)
    });

  // 노드 그룹
  const node = g.append('g').attr('class', 'graph-nodes')
    .selectAll('g.graph-node').data(nodes).enter().append('g')
    .attr('class', 'graph-node')
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end', (event, d) => {
        if (!event.active) sim.alphaTarget(0);
        // v6.15.5: 드래그 후 fx/fy 유지 → 노드 위치 고정 (사용자 요청).
        // 시뮬레이션이 다시 끌어당기지 않음. 더블클릭 시 해제 (아래 dblclick 핸들러).
        // 고정된 노드는 시각적으로 약간 다른 stroke로 표시 (UX 힌트).
        d.fixed = true;
        d3.select(event.sourceEvent.target.parentNode).select('circle')
          .attr('stroke', '#0f172a').attr('stroke-width', 2.5);
      })
    )
    .on('dblclick', (event, d) => {
      // v6.15.5: 더블클릭 시 위치 고정 해제 (시뮬레이션 복귀)
      d.fx = null; d.fy = null;
      d.fixed = false;
      d3.select(event.currentTarget).select('circle')
        .attr('stroke', '#fff').attr('stroke-width', 1.8);
      sim.alphaTarget(0.3).restart();
      setTimeout(() => sim.alphaTarget(0), 500);
      event.stopPropagation();
    })
    .on('click', (event, d) => {
      // 엔티티 상세로 이동
      state.view = 'entities';
      state.selectedEntityId = d.id;
      // nav-item active 토글
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      const navEnt = document.querySelector('.nav-item[data-view="entities"]');
      if (navEnt) navEnt.classList.add('active');
      syncUrl();  // v6.5: 그래프 노드 클릭 → 엔티티 view 이동 시 URL 갱신
      renderContent();
    });

  node.append('circle')
    .attr('r', d => 10 + Math.sqrt(d.mentions || 1) * 2.8)
    .attr('fill', d => ENTITY_TYPE_COLOR[d.type] || '#888')
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.8);

  // v5.0: SVG 노드 라벨 폰트 11 → 16 (50% 상향)
  node.append('text')
    .attr('dy', d => -(15 + Math.sqrt(d.mentions || 1) * 2.8))
    .attr('text-anchor', 'middle')
    .attr('font-size', 16)
    .attr('font-weight', 500)
    .attr('fill', '#1f2937')
    .attr('stroke', '#fff')
    .attr('stroke-width', 3)
    .attr('paint-order', 'stroke fill')
    .text(d => d.name);

  node.append('title')
    .text(d => `${d.name} [${ENTITY_TYPE_LABEL[d.type] || d.type}]\n언급 ${d.mentions}건 · 평균 ${d.avgScore}`);

  sim.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

// v6.0 (P2-3): escapeHtml / escapeHtmlWithMark / formatKoreanDate 는 app.util.js로 이동됨.

document.addEventListener('DOMContentLoaded', init);
